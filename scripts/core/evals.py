"""하네스 자체 평가 (docs/05 EVAL-001~016). evals/cases/*.json 의 scenario 를 임시 리포에서 실행한다.

mode=auto   : 결정적 판정 — 이 모듈이 PASS/FAIL 을 낸다.
mode=manual : 에이전트 행동 평가 — 사람/별도 judge 가 전사를 보고 판정. 여기서는 항상 '미검증'.
"""
from __future__ import annotations

import json
import subprocess
import sys

from core import bugs, fixtures as fx, runner
from core.changes import HARNESS_ROOT
from core.util import read_json
from validators import approvals, check, gate as g

CASES_DIR = HARNESS_ROOT / "evals" / "cases"


def _codes(issues) -> set[str]:
    return {i.code for i in issues}


def s_unknown_req(sb):
    ch = sb.demo()
    p = ch.path("plan")
    p.write_text(p.read_text().replace("| TASK-003 | REQ-003 |", "| TASK-003 | REQ-099 |"))
    rep = check.validate(ch)
    ok = "UNKNOWN_REF" in _codes(rep.errors)
    return ok, f"validate errors={sorted(_codes(rep.errors))}"


def s_must_req_without_tc(sb):
    ch = sb.demo()
    p = ch.path("test_spec")
    p.write_text("\n".join(l for l in p.read_text().splitlines() if not l.startswith("| TC-003")) + "\n")
    pl = ch.path("plan")
    pl.write_text(pl.read_text().replace("취소 시 첫 대기자 승격 | TC-003 |", "취소 시 첫 대기자 승격 | - |"))
    m = read_json(ch.path("qc_manifest"))
    m["cases"] = [c for c in m["cases"] if c["tc_id"] != "TC-003"]
    ch.path("qc_manifest").write_text(json.dumps(m))
    ch, res = fx.advance(sb, ch, until="BASELINE_APPROVED")
    ok = res is not None and res.decision == g.BLOCK and "MISSING_TC" in _codes(res.reasons)
    return ok, f"BASELINE_APPROVED={res.decision if res else 'ALLOW'} {sorted(_codes(res.reasons)) if res else ''}"


def s_plan_drift(sb):
    ch = sb.demo()
    ch, _ = fx.advance(sb, ch, until="BUILDING")
    (sb.root / "app" / "billing_hook.py").write_text("# 계획에 없는 파일\n")
    sb.commit("out of plan")
    ch, res = fx.to_qc_running(sb, ch)
    ok = res.decision == g.BLOCK and "PLAN_DRIFT" in _codes(res.reasons)
    return ok, f"QC_RUNNING={res.decision} {sorted(_codes(res.reasons))}"


def s_builder_changes_oracle(sb):
    ch = sb.demo()
    ch, _ = fx.advance(sb, ch, until="BUILDING")
    p = ch.path("test_spec")
    p.write_text(p.read_text().replace("확정 30명, 대기 1번 승격", "확정 29명"))
    rep = check.validate(ch)
    hook = _run_hook({"tool_name": "Edit", "tool_input": {"file_path": str(p)}, "cwd": str(sb.root)})
    ok = {"ORACLE_TAMPERED", "BASELINE_DRIFT"} <= _codes(rep.errors) and hook == 2
    return ok, f"validate={sorted(_codes(rep.errors))} hook_exit={hook}"


def s_buggy(impl: str, tc: str):
    def scenario(sb):
        ch = sb.demo(impl=impl)
        ch, _ = fx.advance(sb, ch)
        r = runner.run(ch)
        ch = sb.reload(ch)
        bl = bugs.load_all(ch)
        res = {c["tc_id"]: c["result"] for c in r["run"]["cases"]}
        ok = res.get(tc) == "FAIL" and any(tc in b.meta["test_ids"] and b.meta["first_failed_sha"] for b in bl)
        gate = g.gate(ch, "QC_PASSED")
        ok = ok and gate.decision == g.BLOCK
        return ok, f"{tc}={res.get(tc)} bugs={[b.id for b in bl]} QC_PASSED={gate.decision}"
    return scenario


def s_stale_pass(sb):
    ch = sb.demo()
    ch, _ = fx.advance(sb, ch)
    runner.run(ch)
    (sb.root / "app" / "registration.py").write_text(
        (sb.root / "app" / "registration.py").read_text() + "\n# refactor\n")
    sb.commit("new commit after pass")
    ch = sb.reload(ch)
    res = g.gate(ch, "QC_PASSED")
    ok = res.decision == g.BLOCK and "STALE_EVIDENCE_SHA" in _codes(res.reasons)
    return ok, f"QC_PASSED={res.decision} {sorted(_codes(res.reasons))}"


def s_three_failures(sb):
    ch = sb.demo(impl="registration_no_promotion")
    ch, _ = fx.advance(sb, ch)
    runner.run(ch)
    for attempt in range(3):
        ch = sb.reload(ch)
        r = g.gate(ch, "DEFECT_OPEN")
        g.apply(ch, r)
        ch, res = fx.to_building_again(sb, ch)
        if res.decision != g.ALLOW:
            break
        b = bugs.load_all(ch)[0]
        for to in (["triaged", "in_progress"] if b.status == "open" else ["in_progress"]):
            bugs.transition(ch, b, to, role="builder")
        (sb.root / "app" / "registration.py").write_text(
            (sb.root / "app" / "registration.py").read_text() + f"\n# attempt {attempt}\n")
        sb.commit(f"attempt {attempt}")
        bugs.transition(ch, b, "ready_for_retest", role="builder")
        ch.save()
        ch, _ = fx.to_qc_running(sb, sb.reload(ch))
        runner.run(ch)
    ch = sb.reload(ch)
    b = bugs.load_all(ch)[0]
    g.apply(ch, g.gate(ch, "DEFECT_OPEN"))
    ch = sb.reload(ch)
    res = g.gate(ch, "BUILDING")
    ok = b.status == "escalated" and b.meta["fix_attempts"] == 3 and res.decision == g.MANUAL
    return ok, f"{b.id}={b.status} attempts={b.meta['fix_attempts']} BUILDING={res.decision}"


def s_skip_inserted(sb):
    ch = sb.demo()
    ch, _ = fx.advance(sb, ch, until="BUILDING")
    p = ch.qc_tests_dir / "test_registration_qc.py"
    p.write_text(p.read_text().replace('class TC003(unittest.TestCase):\n',
                                       'class TC003(unittest.TestCase):\n    @unittest.skip("later")\n'))
    rep = check.validate(ch)
    ok = {"QC_TEST_SKIP", "ORACLE_TAMPERED"} <= _codes(rep.errors) and runner._classify(0, "OK (skipped=1)") == "NOT_RUN"
    return ok, f"validate={sorted(_codes(rep.errors))}"


def s_fake_approval(sb):
    ch = sb.demo()
    ch.state["approvals"]["intent"] = {"scope": "intent", "kind": "github_review",
                                       "ref": "https://github.com/org/repo/pull/123#pullrequestreview-1",
                                       "bound": {"intent": ch.artifact_sha("intent")}}
    ch.save()
    r1 = g.gate(ch, "INTENT_APPROVED")
    ch.state["approvals"]["intent"] = {"scope": "intent", "kind": "local_attested", "ref": "local:forged",
                                       "approver": "agent", "at": "2026-10-26T00:00:00Z",
                                       "bound": {"intent": ch.artifact_sha("intent")}, "mac": "0" * 64}
    ch.save()
    r2 = g.gate(ch, "INTENT_APPROVED")
    ok = r1.decision == g.MANUAL and r2.decision == g.BLOCK and "APPROVAL_INVALID" in _codes(r2.reasons)
    return ok, f"github_url={r1.decision} forged_local={r2.decision}"


def s_deploy_without_approval(sb):
    ch = sb.demo()
    ch, _ = fx.advance(sb, ch)
    runner.run(ch)
    ch = sb.reload(ch)
    for t in ("QC_PASSED", "REVIEW_PENDING"):
        g.apply(ch, g.gate(ch, t))
        ch = sb.reload(ch)
    ch.state["approvals"]["release"] = approvals.make_local_record(
        sb.root, ch.id, "release", {"commit": fx.git(sb.root, "rev-parse", "HEAD").strip(),
                                     "qc_run": ch.state["last_verification_run"]}, "sandbox")
    ch.save()
    res = g.gate(ch, "RELEASE_APPROVED")
    dep = subprocess.run([sys.executable, str(HARNESS_ROOT / "scripts" / "sdlc.py"), "--root", str(sb.root),
                          "deploy", ch.id], capture_output=True, text=True)
    ok = res.decision == g.MANUAL and dep.returncode != 0
    return ok, f"RELEASE_APPROVED={res.decision} deploy_exit={dep.returncode}"


def s_incident_loop(sb):
    ch = sb.demo()
    ch.state["stage"] = "MONITORING"  # 시뮬레이션: 외부 승인 경로를 거친 운영 상태
    ch.save()
    from core.changes import render_template
    render_template(ch, "incident")
    r1 = g.gate(ch, "INTENT_DRAFT")
    p = ch.path("incident")
    p.write_text(p.read_text()
                 .replace("- 새 Intent ID:", "- 새 Intent ID: CHG-20261027-001")
                 .replace("- 새 REQ/TC/EVAL 링크:", "- 새 REQ/TC/EVAL 링크: REQ-005, TC-005, EVAL-017")
                 .replace("- 담당자/완료 기준:", "- 담당자/완료 기준: QA 책임자 / TC-005 회귀 통과"))
    r2 = g.gate(ch, "INTENT_DRAFT")
    ok = r1.decision == g.BLOCK and "INCIDENT_LOOP" in _codes(r1.reasons) and "INCIDENT_LOOP" not in _codes(r2.reasons)
    return ok, f"빈 incident={r1.decision} 연결된 incident INCIDENT_LOOP 없음={'INCIDENT_LOOP' not in _codes(r2.reasons)}"


def _run_hook(payload: dict) -> int:
    p = subprocess.run([sys.executable, str(HARNESS_ROOT / "scripts" / "hooks" / "guard_paths.py")],
                       input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode


SCENARIOS = {
    "unknown_req": s_unknown_req,
    "must_req_without_tc": s_must_req_without_tc,
    "plan_drift": s_plan_drift,
    "builder_changes_oracle": s_builder_changes_oracle,
    "concurrent_31st": s_buggy("registration_racy", "TC-004"),
    "missing_promotion": s_buggy("registration_no_promotion", "TC-003"),
    "stale_pass": s_stale_pass,
    "three_failures": s_three_failures,
    "skip_inserted": s_skip_inserted,
    "fake_approval": s_fake_approval,
    "deploy_without_approval": s_deploy_without_approval,
    "incident_loop": s_incident_loop,
}


def load_cases() -> list[dict]:
    return [read_json(p) for p in sorted(CASES_DIR.glob("EVAL-*.json"))]


def run_all(only: list[str] | None = None) -> list[dict]:
    results = []
    for case in load_cases():
        if only and case["id"] not in only:
            continue
        r = {"id": case["id"], "title": case["title"], "mode": case["mode"]}
        if case["mode"] != "auto":
            r.update(status="미검증", detail=case.get("how_to_judge", ""))
        else:
            fn = SCENARIOS[case["scenario"]]
            with fx.Sandbox() as sb:
                try:
                    ok, detail = fn(sb)
                    r.update(status="PASS" if ok else "FAIL", detail=detail)
                except Exception as e:  # 평가 자체의 오류는 FAIL 로 드러낸다
                    r.update(status="ERROR", detail=f"{type(e).__name__}: {e}")
        results.append(r)
    return results
