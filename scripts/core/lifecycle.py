"""재기준화(reopen)·Builder 자체 검사 기록."""
from __future__ import annotations

import os
import subprocess

from core import gitutil, hashing, state as sm
from core.util import SdlcError, atomic_write_text, now_iso

REOPEN_CLEARS_BASELINES = {
    "INTENT_DRAFT": ["intent", "spec", "plan", "test_spec", "qc_manifest", "qc_tests"],
    "SPEC_DRAFT": ["spec", "plan", "test_spec", "qc_manifest", "qc_tests"],
    "PLAN_TEST_DRAFT": ["plan", "test_spec", "qc_manifest", "qc_tests"],
}


def reopen(change, to: str, reason: str) -> dict:
    st = change.state
    cur = st["stage"]
    if to not in sm.REOPEN_TARGETS:
        raise SdlcError(f"reopen 목적지는 {sm.REOPEN_TARGETS} 중 하나")
    if sm.STAGES.index(to) >= sm.STAGES.index(cur if cur != "DEFECT_OPEN" else "QC_RUNNING"):
        raise SdlcError(f"{cur} 에서 {to} 로 되돌릴 수 없음 (뒤 단계로만 reopen)")
    if not reason.strip():
        raise SdlcError("reopen 사유 필수")
    cleared_approvals = [s for s in sm.REOPEN_CLEARS[to] if s in st.get("approvals", {})]
    for s in cleared_approvals:
        st["approvals"].pop(s)
    for art in REOPEN_CLEARS_BASELINES[to]:
        st.get("baselines", {}).pop(art, None)
    st["qc_lock"] = {}
    st["build_base_sha"] = None
    if st.get("last_verification_run"):
        st.setdefault("stale_runs", []).append(st["last_verification_run"])
        st["last_verification_run"] = None
    st["stage"] = to
    change.record("reopen", **{"from": cur, "to": to, "reason": reason, "cleared_approvals": cleared_approvals})
    change.save()
    return {"from": cur, "to": to, "cleared_approvals": cleared_approvals}


def build_check(change, cmd: list[str], timeout: int = 900) -> dict:
    if not cmd:
        raise SdlcError("검사 명령이 필요합니다: sdlc build check <id> -- <cmd...>")
    if change.state["stage"] != "BUILDING":
        raise SdlcError(f"build check 는 BUILDING 단계에서만 (현재 {change.state['stage']})")
    root = change.project.root
    n = change.next_counter("build")
    log = change.dir / "build" / f"BUILD-{n:03d}.log"
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        out, code = p.stdout + p.stderr, p.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        out, code = f"{type(e).__name__}: {e}", 127
    atomic_write_text(log, out)
    dirty = gitutil.dirty_paths(root)
    rec = {"at": now_iso(), "cmd": cmd, "exit_code": code, "commit_sha": gitutil.head(root),
           "dirty": bool(dirty) if dirty is not None else True,
           "log_path": log.relative_to(change.dir).as_posix(), "log_sha256": hashing.sha256_file(log)}
    change.state.setdefault("build_checks", []).append(rec)
    change.save()
    return rec
