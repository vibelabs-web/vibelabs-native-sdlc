"""QC 실행기 (`sdlc qc run`): 고정 SHA 에서 qc-manifest 의 TC 명령을 실행하고 RUN-NNN.json 증거를 남긴다.

판정
- PASS    : exit 0, skip/0건 실행 흔적 없음
- FAIL    : exit ≠ 0
- NOT_RUN : skip 또는 실행된 테스트 0건 (PASS 로 집계 금지), manifest 에 명령 없음
- BLOCKED : 명령 실행 불가/시간 초과 (INFRA — PASS 간주 금지)
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from core import bugs, gitutil, hashing
from core.util import SdlcError, atomic_write_json, atomic_write_text, now_iso, read_json
from validators import check, evidence
from validators.paths import safe_join

_SKIP_OUT = re.compile(r"skipped=\d+|\bSKIPPED\b|\b\d+ skipped\b|Ran 0 tests|no tests ran|NO TESTS RAN", re.I)


def _classify(code: int | None, output: str) -> str:
    if code is None:
        return "BLOCKED"
    if code != 0:
        return "FAIL"
    if _SKIP_OUT.search(output):
        return "NOT_RUN"
    return "PASS"


def run(change, *, isolated: bool = False, allow_dirty: bool = False, timeout: int | None = None) -> dict:
    st = change.state
    root = change.project.root
    if st["stage"] != "QC_RUNNING":
        raise SdlcError(f"QC 는 QC_RUNNING 단계에서만 실행 (현재 {st['stage']}) — `sdlc gate {change.id} QC_RUNNING`")
    head = gitutil.head(root)
    if head is None:
        raise SdlcError("git HEAD 없음 — 고정 커밋 없이 QC 증거를 만들 수 없음")
    dirty = gitutil.dirty_paths(root) or []
    if dirty and not allow_dirty:
        raise SdlcError(f"미커밋 변경 {dirty[:5]} — 커밋 후 실행 (--allow-dirty 증거는 게이트에서 무효)")
    rep = check.validate(change)
    if rep.errors:
        raise SdlcError("기준선/오라클 오류 상태에서 QC 실행 거부:\n" + "\n".join(str(i) for i in rep.errors))
    man = read_json(change.path("qc_manifest"))
    tmo = timeout or int(man.get("timeout_seconds", 300))

    n = change.next_counter("run")
    run_id = f"RUN-{n:03d}"
    log_dir = change.evidence_dir / run_id
    log_dir.mkdir(parents=True, exist_ok=True)

    workdir, wt = root, None
    if isolated:
        wt = Path(tempfile.mkdtemp(prefix=f"sdlc-qc-{run_id}-"))
        shutil.rmtree(wt)
        if not gitutil.worktree_add(root, wt, head):
            raise SdlcError("격리 worktree 생성 실패")
        dest = wt / change.dir.relative_to(root)
        dest.mkdir(parents=True, exist_ok=True)
        if change.qc_tests_dir.is_dir():
            shutil.copytree(change.qc_tests_dir, dest / "qc-tests", dirs_exist_ok=True)
        shutil.copy2(change.path("qc_manifest"), dest / "qc-manifest.json")
        workdir = wt

    started = now_iso()
    commands, cases = [], []
    try:
        for c in man["cases"]:
            tc = c["tc_id"]
            cwd = safe_join(workdir, c.get("cwd", "."))
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "SDLC_TC_ID": tc,
                   "SDLC_CHANGE_DIR": str(workdir / change.dir.relative_to(root))}
            try:
                p = subprocess.run(c["cmd"], cwd=cwd, capture_output=True, text=True, timeout=tmo, env=env)
                code, out = p.returncode, p.stdout + p.stderr
            except FileNotFoundError as e:
                code, out = None, f"INFRA: 명령 없음 {e}"
            except subprocess.TimeoutExpired:
                code, out = None, f"INFRA: {tmo}s 시간 초과"
            log = log_dir / f"{tc}.log"
            atomic_write_text(log, out)
            result = _classify(code, out)
            commands.append({"tc_id": tc, "cmd": " ".join(c["cmd"]), "exit_code": code,
                             "log_path": log.relative_to(change.dir).as_posix(),
                             "log_sha256": hashing.sha256_file(log)})
            cases.append({"tc_id": tc, "result": result, "evidence": log.relative_to(change.dir).as_posix(),
                          "summary": out.strip().splitlines()[-1][:200] if out.strip() else ""})
    finally:
        if wt is not None:
            gitutil.worktree_remove(root, wt)
            shutil.rmtree(wt, ignore_errors=True)

    mapped = {c["tc_id"] for c in cases}
    for tc in sorted(set((rep.index or {}).get("tcs", {})) - mapped):
        cases.append({"tc_id": tc, "result": "NOT_RUN", "evidence": None, "summary": "qc-manifest 에 실행 명령 없음"})

    b = st.get("baselines", {})
    run_doc = {
        "run_id": run_id, "change_id": change.id, "commit_sha": head,
        "spec_sha": b.get("spec"), "test_spec_sha": b.get("test_spec"),
        "qc_manifest_sha": b.get("qc_manifest"), "qc_tests_sha": b.get("qc_tests"),
        "environment": f"{'isolated-worktree' if isolated else 'local-cwd'}:{platform.system().lower()}"
                       f"-py{platform.python_version()}",
        "worktree_dirty": bool(dirty), "started_at": started, "finished_at": now_iso(),
        "commands": commands, "cases": cases, "verifier_role": "qc-verifier",
        "evidence_level": "E1",
    }
    run_doc["report_sha256"] = evidence.report_digest(run_doc)
    atomic_write_json(evidence.run_path(change, run_id), run_doc)
    st["last_verification_run"] = run_id
    change.record("qc_run", run=run_id, commit=head,
                  results={c["tc_id"]: c["result"] for c in cases})
    bug_events = _update_bugs(change, run_doc, rep)
    change.save()
    return {"run": run_doc, "bug_events": bug_events}


def _update_bugs(change, run_doc: dict, rep) -> list[str]:
    events: list[str] = []
    sha = run_doc["commit_sha"]
    rid = run_doc["run_id"]
    budget = int(change.state.get("retry_budget", {}).get("per_defect", 3))
    all_bugs = bugs.load_all(change)
    idx = rep.index or {"tcs": {}, "reqs": {}}
    parsed_tcs = {c.id: c for c in rep.parsed["test_spec"].tcs} if "test_spec" in rep.parsed else {}
    for case in run_doc["cases"]:
        tc, result = case["tc_id"], case["result"]
        related = [b for b in all_bugs if tc in (b.meta.get("test_ids") or []) and not b.resolved]
        if result == "FAIL":
            retest = [b for b in related if b.status == "ready_for_retest"]
            for b in retest:
                if b.meta.get("last_failed_sha") == sha:
                    events.append(f"{b.id}: 같은 SHA {sha[:12]} 재검증 — 새 커밋 없음, 상태 유지")
                    continue
                b.meta["fix_attempts"] = int(b.meta.get("fix_attempts", 0)) + 1
                b.meta["last_failed_sha"] = sha
                bugs.transition(change, b, "reopened", role="qc-verifier", ref=f"{rid} FAIL", via_qc=True)
                if b.meta["fix_attempts"] >= budget:
                    bugs.transition(change, b, "escalated", role="qc-verifier",
                                    ref=f"수정 {b.meta['fix_attempts']}회 실패 ≥ 예산 {budget}")
                    change.state.setdefault("blocked_reasons", []).append(
                        f"{b.id} 에스컬레이션: 수정 {b.meta['fix_attempts']}회 실패 — 사람의 결정 필요")
                    events.append(f"{b.id}: reopened → escalated (재시도 예산 {budget} 소진)")
                else:
                    events.append(f"{b.id}: reopened (수정 시도 {b.meta['fix_attempts']}/{budget})")
            if not related:
                tcd = idx["tcs"].get(tc, {})
                reqs = tcd.get("reqs", [])
                must = any(idx["reqs"].get(r, {}).get("must") for r in reqs)
                then = parsed_tcs[tc].then if tc in parsed_tcs else "test-spec 기대 결과"
                cmd = next((c["cmd"] for c in run_doc["commands"] if c["tc_id"] == tc), "?")
                nb = bugs.create(change, req_ids=reqs, tc_ids=[tc], title=f"{tc} 실패 ({', '.join(reqs)})",
                                 severity="high" if must else "medium", expected=then,
                                 actual=case.get("summary") or "로그 참조",
                                 repro=[f"commit {sha}", f"`{cmd}`", f"로그 {case['evidence']}"],
                                 commit_sha=sha, run_id=rid, log_ref=case["evidence"])
                all_bugs.append(nb)
                events.append(f"{nb.id}: 신규 결함 ({tc})")
        elif result == "PASS":
            for b in related:
                if b.status != "ready_for_retest":
                    events.append(f"{b.id}: {tc} PASS 지만 상태 {b.status} — Builder 가 ready_for_retest 로 넘겨야 검증")
                    continue
                if b.meta.get("last_failed_sha") == sha:
                    events.append(f"{b.id}: 실패했던 SHA 와 동일 — verified_fixed 판정 보류")
                    continue
                others = [t for t in b.meta.get("test_ids") or []
                          if next((c["result"] for c in run_doc["cases"] if c["tc_id"] == t), "NOT_RUN") != "PASS"]
                if others:
                    events.append(f"{b.id}: 연결 TC {others} 미통과 — 보류")
                    continue
                b.meta["verified_run"] = rid
                bugs.transition(change, b, "verified_fixed", role="qc-verifier", ref=f"{rid} @ {sha[:12]}", via_qc=True)
                events.append(f"{b.id}: verified_fixed ({rid})")
    return events
