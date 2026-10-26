"""계획 드리프트: 빌드 시작 SHA 이후 바뀐 파일이 plan.md TASK 의 변경 파일 열에 선언됐는지 (EVAL-005)."""
from __future__ import annotations

import fnmatch
import re

from core import gitutil
from validators.issues import Issue, blocker, warn

_TOKEN_RE = re.compile(r"[`'\"]?([\w./*\-]+)[`'\"]?")


def declared_paths(tasks) -> list[str]:
    out = []
    for t in tasks:
        for tok in _TOKEN_RE.findall(t.files or ""):
            if "/" in tok or re.search(r"\.\w+$", tok):
                out.append(tok[2:] if tok.startswith("./") else tok)
    return out


def _covered(path: str, declared: list[str]) -> bool:
    for d in declared:
        d2 = d.rstrip("/")
        if path == d2 or path.startswith(d2 + "/") or fnmatch.fnmatch(path, d):
            return True
    return False


def check(change, plan) -> tuple[list[Issue], list[str]]:
    base = change.state.get("build_base_sha")
    if not base:
        return [warn("DRIFT_UNCHECKED", "build_base_sha 없음 — 드리프트 미검증")], []
    changed = gitutil.changed_files(change.project.root, base)
    if changed is None:
        return [blocker("DRIFT_UNKNOWN", f"git diff {base[:12]}..HEAD 실패 — 드리프트 확인 불가")], []
    changed = [p for p in changed if not p.startswith(".sdlc/")]
    declared = declared_paths(plan.tasks if plan else [])
    if not declared:
        return [warn("DRIFT_UNCHECKED", "plan.md 에 파일 경로가 선언되지 않음 — 드리프트 미검증")], []
    out = [p for p in changed if not _covered(p, declared)]
    issues = [blocker("PLAN_DRIFT", f"계획 밖 변경: {p} — 중지→영향 분석→plan 개정·재승인", "plan.md") for p in out]
    return issues, out
