"""QC 소유 오라클 잠금과 변조·skip 탐지 (설계서 §6.3 테스트 누수 방지, 작업지시서 Phase 4-2)."""
from __future__ import annotations

import re
from pathlib import Path

from core import hashing
from core.util import now_iso
from validators.issues import Issue, err, warn

SKIP_PATTERNS = [
    r"@unittest\.skip", r"\.skipTest\(", r"unittest\.SkipTest", r"@pytest\.mark\.(skip|xfail)",
    r"pytest\.(skip|xfail)\(", r"\b(it|test|describe)\.skip\(", r"\bx(it|describe|test)\(",
    r"\.only\(", r"t\.Skip\(", r"#\[ignore\]",
]
_SKIP_RE = re.compile("|".join(SKIP_PATTERNS))


def locked_files(change) -> list[Path]:
    files = [change.path("test_spec"), change.path("qc_manifest")]
    d = change.qc_tests_dir
    if d.is_dir():
        files += [p for p in sorted(d.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    return files


def make_lock(change) -> dict:
    return {
        "locked_at": now_iso(),
        "files": {p.relative_to(change.dir).as_posix(): hashing.git_blob_sha(p)
                  for p in locked_files(change) if p.is_file()},
    }


def find_skips(path: Path) -> list[tuple[int, str]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [(n, line.strip()) for n, line in enumerate(lines, 1) if _SKIP_RE.search(line)]


def check(change) -> list[Issue]:
    issues: list[Issue] = []
    lock = change.state.get("qc_lock") or {}
    files = lock.get("files", {})
    for rel, sha in files.items():
        p = change.dir / rel
        if not p.is_file():
            issues.append(err("QC_TEST_DELETED", f"잠긴 QC 자산 {rel} 삭제됨 — 승인 없는 삭제 금지", rel))
        elif hashing.git_blob_sha(p) != sha:
            issues.append(err("ORACLE_TAMPERED",
                              f"잠긴 QC 자산 {rel} 가 기준선 이후 변경됨 — 오라클 변경은 reopen + QA/PO 재승인 필요", rel))
    if files:
        for p in locked_files(change):
            rel = p.relative_to(change.dir).as_posix()
            if rel not in files:
                issues.append(err("QC_TEST_ADDED", f"기준선에 없던 QC 자산 {rel} — 재승인 필요", rel))
    d = change.qc_tests_dir
    if d.is_dir():
        for p in sorted(d.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                for n, line in find_skips(p):
                    issues.append(err("QC_TEST_SKIP", f"QC 테스트에 skip/only 표식: {line}",
                                      p.relative_to(change.dir).as_posix(), n))
    return issues


def scan_product_tests(root: Path, globs=("tests/**/*.py", "test/**/*.py", "**/*_test.py", "**/*.test.*")) -> list[Issue]:
    seen: set[Path] = set()
    issues: list[Issue] = []
    for g in globs:
        for p in root.glob(g):
            if p in seen or ".sdlc" in p.parts or "node_modules" in p.parts or not p.is_file():
                continue
            seen.add(p)
            for n, line in find_skips(p):
                issues.append(warn("SKIP_IN_TESTS", f"skip 표식 — 해당 검사는 미검증으로 취급: {line}",
                                   p.relative_to(root).as_posix(), n))
    return issues
