#!/usr/bin/env python3
"""Claude Code PreToolUse 훅: 잠긴 QC 오라클·상태·증거 파일을 도구로 직접 고치지 못하게 막는다.

소프트 제약이다 — 셸·다른 프로세스로 우회할 수 있다. 최종 강제는 CI(`sdlc ci`)와 보호 브랜치가 맡는다
(docs/security-limitations.md). exit 2 = 차단(stderr 가 에이전트에게 전달됨), exit 0 = 통과.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
ALWAYS_PROTECTED = ("state.json", "evidence/", "build/")
BASH_WRITE_RE = re.compile(r"(\brm\b|\bmv\b|\bcp\b|sed\s+-i|\btee\b|\btruncate\b|>>?|\bchmod\b|\bln\b|open\(.+['\"]w)")


def _change_root(path: Path) -> tuple[Path, str] | None:
    parts = path.parts
    for i in range(len(parts) - 2):
        if parts[i] == ".sdlc" and parts[i + 1] == "changes":
            return Path(*parts[: i + 3]), Path(*parts[i + 3:]).as_posix() if len(parts) > i + 3 else ""
    return None


def protected_reason(path: Path) -> str | None:
    found = _change_root(path)
    if not found:
        return None
    cdir, rel = found
    if not rel:
        return None
    if any(rel == p or rel.startswith(p) for p in ALWAYS_PROTECTED):
        return f"{rel} 는 sdlc CLI 만 쓸 수 있음 (상태·증거 위조 방지)"
    try:
        st = json.loads((cdir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    lock = (st.get("qc_lock") or {}).get("files", {})
    if lock and (rel in lock or rel.startswith("qc-tests/")):
        return (f"{rel} 는 승인된 QC 오라클(기준선 잠금) — Builder 수정 금지. 기대값 변경은 "
                f"`sdlc reopen {cdir.name} --to PLAN_TEST_DRAFT --reason ...` 후 QA/PO 재승인")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    if tool in WRITE_TOOLS:
        fp = ti.get("file_path") or ti.get("notebook_path")
        if not fp:
            return 0
        p = Path(fp) if os.path.isabs(fp) else cwd / fp
        reason = protected_reason(Path(os.path.realpath(p)))
        if reason:
            print(f"[sdlc guard] 차단: {reason}", file=sys.stderr)
            return 2
    if tool == "Bash":
        cmd = ti.get("command", "")
        if ".sdlc/changes" in cmd and "sdlc.py" not in cmd and BASH_WRITE_RE.search(cmd):
            for m in re.finditer(r"[^\s'\"]*\.sdlc/changes/[^\s'\"]+", cmd):
                p = Path(m.group(0)) if os.path.isabs(m.group(0)) else cwd / m.group(0)
                reason = protected_reason(Path(os.path.realpath(p)))
                if reason:
                    print(f"[sdlc guard] 셸 쓰기 차단: {reason}", file=sys.stderr)
                    return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
