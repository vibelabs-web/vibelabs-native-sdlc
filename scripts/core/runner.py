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
import time
from concurrent.futures import ThreadPoolExecutor
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


def _select_cases(change, man: dict, rep, retest: bool) -> tuple[list[dict], dict[str, str]]:
    """이번 실행에 돌릴 케이스와, 등급 정책으로 생략한 TC({tc: 사유})를 고른다.

    미해결 BUG 에 연결된 TC 는 어떤 경우에도 생략하지 않는다.
    """
    cases = man["cases"]
    open_tcs = {t for b in bugs.load_all(change) if not b.resolved for t in (b.meta.get("test_ids") or [])}
    if retest:
        groups = {c["regression_group"] for c in cases if c["tc_id"] in open_tcs and c.get("regression_group")}
        chosen = [c for c in cases if c["tc_id"] in open_tcs or c.get("regression_group") in groups]
        if not chosen:
            raise SdlcError("재검증 대상 TC 없음 — 미해결 BUG 에 연결된 TC 가 없습니다. 전체 실행을 쓰세요 (--retest 없이)")
        return chosen, {}
    if change.state.get("risk_level") != "lite" or not rep.index:
        return cases, {}
    idx = rep.index
    must = {tc for tc, v in idx["tcs"].items() if any(idx["reqs"].get(r, {}).get("must") for r in v["reqs"])}
    chosen = [c for c in cases if c["tc_id"] in must | open_tcs]
    picked = {c["tc_id"] for c in chosen}
    return chosen, {c["tc_id"]: "lite 등급 — 비필수 TC 생략" for c in cases if c["tc_id"] not in picked}


def _exec(cmd: list[str], cwd: Path, env: dict, tmo: int) -> tuple[int | None, str, int]:
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=tmo, env=env)
        code, out = p.returncode, p.stdout + p.stderr
    except FileNotFoundError as e:
        code, out = None, f"INFRA: 명령 없음 {e}"
    except subprocess.TimeoutExpired:
        code, out = None, f"INFRA: {tmo}s 시간 초과"
    return code, out, int((time.monotonic() - t0) * 1000)


def _run_setup(change, man: dict, workdir: Path, log_dir: Path, env: dict) -> tuple[list[dict], str | None]:
    """manifest setup 을 한 번만 순서대로 실행한다. 실패하면 (기록, 실패 사유)."""
    tmo = int(man.get("setup_timeout_seconds", 900))
    records: list[dict] = []
    for n, step in enumerate(man.get("setup") or [], start=1):
        code, out, ms = _exec(step["cmd"], safe_join(workdir, step.get("cwd", ".")), env, tmo)
        log = log_dir / f"setup-{n}.log"
        atomic_write_text(log, out)
        records.append({"cmd": " ".join(step["cmd"]), "exit_code": code, "duration_ms": ms,
                        "log_path": log.relative_to(change.dir).as_posix(), "log_sha256": hashing.sha256_file(log)})
        if code != 0:
            return records, f"setup {n}단계 실패 (exit {code}) — {log.name} 참조"
    return records, None


def run(change, *, isolated: bool = False, allow_dirty: bool = False, timeout: int | None = None,
        retest: bool = False) -> dict:
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
    selected, skipped = _select_cases(change, man, rep, retest)

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

    base_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                "SDLC_CHANGE_DIR": str(workdir / change.dir.relative_to(root))}

    def run_case(c: dict) -> tuple[dict, dict]:
        tc = c["tc_id"]
        code, out, ms = _exec(c["cmd"], safe_join(workdir, c.get("cwd", ".")), {**base_env, "SDLC_TC_ID": tc}, tmo)
        log = log_dir / f"{tc}.log"
        atomic_write_text(log, out)
        evidence_path = log.relative_to(change.dir).as_posix()
        return ({"tc_id": tc, "cmd": " ".join(c["cmd"]), "exit_code": code, "log_path": evidence_path,
                 "log_sha256": hashing.sha256_file(log)},
                {"tc_id": tc, "result": _classify(code, out), "evidence": evidence_path, "duration_ms": ms,
                 "summary": out.strip().splitlines()[-1][:200] if out.strip() else ""})

    started = now_iso()
    t0 = time.monotonic()
    commands, cases, setup = [], [], []
    try:
        setup, setup_error = _run_setup(change, man, workdir, log_dir, base_env)
        if setup_error:
            # 환경 문제이지 제품 결함이 아니다 — BLOCKED 로 남기고 BUG 는 만들지 않는다
            cases = [{"tc_id": c["tc_id"], "result": "BLOCKED", "evidence": None, "summary": f"INFRA: {setup_error}"}
                     for c in selected]
        else:
            workers = min(int(man.get("max_parallel", 1)), len(selected)) or 1
            with ThreadPoolExecutor(max_workers=workers) as pool:
                # map 은 입력 순서를 유지한다 — 증거의 케이스 순서는 병렬이어도 manifest 순서
                for command, case in pool.map(run_case, selected):
                    commands.append(command)
                    cases.append(case)
    finally:
        if wt is not None:
            gitutil.worktree_remove(root, wt)
            shutil.rmtree(wt, ignore_errors=True)

    cases += [{"tc_id": tc, "result": "NOT_RUN", "evidence": None, "summary": why, "skipped_by": "risk"}
              for tc, why in skipped.items()]
    if not retest:
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
        "scope": "retest" if retest else "full", "duration_ms": int((time.monotonic() - t0) * 1000),
        "setup": setup, "commands": commands, "cases": cases, "verifier_role": "qc-verifier",
        "evidence_level": "E1",
    }
    run_doc["report_sha256"] = evidence.report_digest(run_doc)
    atomic_write_json(evidence.run_path(change, run_id), run_doc)
    if not retest:  # 부분 실행은 게이트 증거가 될 수 없다
        st["last_verification_run"] = run_id
    change.record("qc_run", run=run_id, commit=head, scope=run_doc["scope"],
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
