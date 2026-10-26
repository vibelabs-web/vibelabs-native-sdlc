"""작업지시서 §5 인수 테스트 매트릭스 AT-01~16.

AT-01/02 는 에이전트 대화 행동이 본질이라 여기서는 CLI 산출물 구조만 검증한다 (행동은 evals EVAL-001/002 수동 평가).
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from _base import SCRIPTS, SandboxCase, fx
from core import bugs, lifecycle, runner
from core.changes import render_template
from core.util import read_json
from validators import approvals, artifacts, check, gate as g


class AT01_IntentDraft(SandboxCase):
    def test_new_creates_intent_with_tagged_sources(self):
        code, data = self.cli_json("new", "--title", "행사 대기자 기능", "--source", "chat:2026-10-26")
        self.assertEqual(code, 0)
        ch = self.sb.project.load(data["change_id"])
        self.assertEqual(ch.state["stage"], "INTENT_DRAFT")
        text = ch.path("intent").read_text()
        for sec in ("## Open questions", "## Source of truth / Confirmations", "confirmed/assumed/proposed/open"):
            self.assertIn(sec, text)
        rep = check.validate(ch)
        self.assertEqual(rep.errors, [], "새 intent 는 구조 오류가 없어야 함")
        self.assertIn("PLACEHOLDER", self.codes(rep.blockers), "빈 템플릿은 승인 차단")


class AT02_AmbiguousPolicyStaysOpen(SandboxCase):
    def test_tc_for_open_req_is_rejected(self):
        ch = self.sb.demo()
        sp = ch.path("spec")
        text = sp.read_text()
        row3 = next(l for l in text.splitlines() if l.startswith("| REQ-003"))
        sp.write_text(text.replace(row3, row3 + "\n| REQ-004 | 중복 신청 처리 | 데모 Intent | open | 미결정 |"))
        rep = check.validate(ch)
        self.assertFalse(rep.index["reqs"]["REQ-004"]["must"], "미결정 REQ 는 필수 커버리지에서 제외")
        ts = ch.path("test_spec")
        text = ts.read_text()
        row4 = next(l for l in text.splitlines() if l.startswith("| TC-004"))
        ts.write_text(text.replace(row4, row4 + "\n| TC-005 | REQ-004 | 기존 신청자 | 같은 이름 재신청 | 거절 | API |"))
        rep = check.validate(ch)
        self.assertIn("ORACLE_FOR_OPEN_REQ", self.codes(rep.errors))

    def test_blocking_open_question_blocks_intent(self):
        ch = self.sb.demo()
        p = ch.path("intent")
        p.write_text(p.read_text() + "\n| ID | 질문 | 영향 | 담당 결정자 | 차단 여부 | 상태 |\n|---|---|---|---|---|---|\n"
                                     "| OPEN-001 | 중복 신청? | 정원 | PO | yes | unanswered |\n")
        fx.approve(ch, "intent")
        res = g.gate(self.sb.reload(ch), "INTENT_APPROVED")
        self.assertEqual(res.decision, g.BLOCK)
        self.assertIn("OPEN_BLOCKING", self.codes(res.reasons))


class AT03_NoApprovalNoSpec(SandboxCase):
    def test_gate_without_approval(self):
        ch = self.sb.demo()
        self.assertEqual(g.gate(ch, "INTENT_APPROVED").decision, g.MANUAL)
        res = g.gate(ch, "SPEC_APPROVED")
        self.assertIn("INVALID_TRANSITION", self.codes(res.reasons))
        code, _ = self.cli_json("gate", ch.id, "INTENT_APPROVED")
        self.assertEqual(code, 3)


class AT04_MissingTc(SandboxCase):
    def test(self):
        from core import evals
        ok, detail = evals.s_must_req_without_tc(self.sb)
        self.assertTrue(ok, detail)


class AT05_UnknownReq(SandboxCase):
    def test(self):
        ch = self.sb.demo()
        p = ch.path("test_spec")
        p.write_text(p.read_text().replace("| TC-002 | REQ-002 |", "| TC-002 | REQ-077 |"))
        code, data = self.cli_json("validate", ch.id)
        self.assertEqual(code, 1)
        msgs = [i["message"] for i in data["changes"][0]["issues"] if i["code"] == "UNKNOWN_REF"]
        self.assertTrue(any("REQ-077" in m for m in msgs))


class AT06_PlanChangedAfterApproval(SandboxCase):
    def test(self):
        ch = self.sb.demo()
        ch, _ = fx.advance(self.sb, ch, until="BUILDING")
        p = ch.path("plan")
        p.write_text(p.read_text() + "\n- 추가 위험: 캐시\n")
        rep = check.validate(ch)
        self.assertIn("BASELINE_DRIFT", self.codes(rep.errors))
        self.assertIn("evidence", rep.stale["plan"])
        lifecycle.build_check(ch, fx.self_check_cmd())
        res = g.gate(self.sb.reload(ch), "QC_RUNNING")
        self.assertIn("APPROVAL_STALE", self.codes(res.reasons))
        r = lifecycle.reopen(self.sb.reload(ch), "PLAN_TEST_DRAFT", "plan 개정")
        self.assertIn("plan_test", r["cleared_approvals"])
        ch = self.sb.reload(ch)
        self.assertEqual(check.validate(ch).errors, [])
        self.assertEqual(g.gate(ch, "BASELINE_APPROVED").decision, g.MANUAL, "재승인 필요")


class AT07_OracleTamper(SandboxCase):
    def test(self):
        from core import evals
        ok, detail = evals.s_builder_changes_oracle(self.sb)
        self.assertTrue(ok, detail)


class AT08_StalePass(SandboxCase):
    def test(self):
        from core import evals
        ok, detail = evals.s_stale_pass(self.sb)
        self.assertTrue(ok, detail)


class AT09_MissingPromotionCreatesBug(SandboxCase):
    def test(self):
        ch = self.sb.demo(impl="registration_no_promotion")
        ch, _ = fx.advance(self.sb, ch)
        r = runner.run(ch)
        self.assertEqual({c["tc_id"]: c["result"] for c in r["run"]["cases"]}["TC-003"], "FAIL")
        ch = self.sb.reload(ch)
        b = bugs.load_all(ch)[0]
        self.assertEqual(b.meta["status"], "open")
        self.assertEqual(b.meta["requirement_ids"], ["REQ-003"])
        self.assertEqual(b.meta["first_failed_sha"], r["run"]["commit_sha"])
        self.assertIn("evidence/RUN-001/TC-003.log", b.text)
        self.assertIn("대기 1번 승격", b.text, "기대값은 test-spec 에서 온다")
        self.assertEqual(g.gate(ch, "DEFECT_OPEN").decision, g.ALLOW)


class AT10_FixAndRegression(SandboxCase):
    def test(self):
        ch = self.sb.demo(impl="registration_no_promotion")
        ch, _ = fx.advance(self.sb, ch)
        runner.run(ch)
        ch = self.sb.reload(ch)
        g.apply(ch, g.gate(ch, "DEFECT_OPEN"))
        ch, res = fx.to_building_again(self.sb, self.sb.reload(ch))
        self.assertEqual(res.decision, g.ALLOW)
        b = bugs.load_all(ch)[0]
        with self.assertRaises(Exception):
            bugs.transition(ch, b, "verified_fixed", role="builder")
        for to in ("triaged", "in_progress"):
            bugs.transition(ch, b, to, role="builder")
        self.sb.use_impl("correct")
        self.sb.commit("fix: promote first waitlisted on cancel")
        bugs.transition(ch, b, "ready_for_retest", role="builder")
        ch.save()
        ch, res = fx.to_qc_running(self.sb, self.sb.reload(ch))
        self.assertEqual(res.decision, g.ALLOW, res.to_dict())
        r = runner.run(ch)
        self.assertEqual(r["run"]["run_id"], "RUN-002")
        self.assertTrue(all(c["result"] == "PASS" for c in r["run"]["cases"]), "인접 회귀 포함 전체 재실행")
        ch = self.sb.reload(ch)
        b = bugs.load_all(ch)[0]
        self.assertEqual(b.status, "verified_fixed")
        self.assertEqual(b.meta["verified_run"], "RUN-002")
        self.assertEqual(g.gate(ch, "QC_PASSED").decision, g.ALLOW)


class AT11_RetryBudget(SandboxCase):
    def test(self):
        from core import evals
        ok, detail = evals.s_three_failures(self.sb)
        self.assertTrue(ok, detail)


class AT12_HighRisk(SandboxCase):
    def test(self):
        code, data = self.cli_json("new", "--title", "로그인 인증 및 개인정보 수정")
        self.assertEqual(data["risk_level"], "high")
        code, data = self.cli_json("new", "--title", "관리자 비밀번호 재설정", "--risk", "lite")
        self.assertEqual(data["risk_level"], "high", "하향 불가")
        ch = self.sb.project.load(data["change_id"])
        p = ch.path("intent")
        demo_intent = (fx.HARNESS_ROOT / "examples/event-registration/intent.md").read_text()
        p.write_text(demo_intent.replace("CHG-DEMO-001", ch.id))
        fx.approve(ch, "intent")
        res = g.gate(self.sb.reload(ch), "INTENT_APPROVED")
        self.assertEqual(res.decision, g.MANUAL)
        self.assertTrue(any("E2" in m for m in res.manual))


class AT13_SkipIsNotPass(SandboxCase):
    def test(self):
        ch = self.sb.demo()
        m = read_json(ch.path("qc_manifest"))
        for c in m["cases"]:
            if c["tc_id"] == "TC-002":
                c["cmd"] = [sys.executable, "-c", "print('OK (skipped=1)')"]
        ch.path("qc_manifest").write_text(json.dumps(m))
        self.sb.commit("manifest")
        ch, _ = fx.advance(self.sb, self.sb.reload(ch))
        r = runner.run(ch)
        res = {c["tc_id"]: c["result"] for c in r["run"]["cases"]}
        self.assertEqual(res["TC-002"], "NOT_RUN")
        gr = g.gate(self.sb.reload(ch), "QC_PASSED")
        self.assertEqual(gr.decision, g.BLOCK)
        self.assertIn("REQ_NOT_VERIFIED", self.codes(gr.reasons))


class AT14_ApprovalStringOnly(SandboxCase):
    def test_status_approved_is_not_evidence(self):
        ch = self.sb.demo()
        p = ch.path("intent")
        p.write_text(p.read_text().replace("status: draft", "status: approved").replace(
            "approval_ref: null", "approval_ref: https://github.com/org/repo/pull/1#pullrequestreview-9"))
        rep = check.validate(ch)
        self.assertIn("STATUS_NOT_EVIDENCE", self.codes(rep.issues))
        self.assertEqual(g.gate(ch, "INTENT_APPROVED").decision, g.MANUAL)

    def test_fake_records(self):
        from core import evals
        ok, detail = evals.s_fake_approval(self.sb)
        self.assertTrue(ok, detail)

    def test_approve_requires_tty(self):
        ch = self.sb.demo()
        p = self.cli("approve", ch.id, "intent", stdin=ch.id + "\n")
        self.assertEqual(p.returncode, 2)
        self.assertIn("TTY", p.stderr)
        self.assertEqual(self.sb.reload(ch).state["approvals"], {})

    def test_tampered_signed_record(self):
        ch = self.sb.demo()
        fx.approve(ch, "intent")
        ch = self.sb.reload(ch)
        ch.state["approvals"]["intent"]["approver"] = "someone-else"
        ch.save()
        self.assertEqual(approvals.verify(self.sb.root, ch.id, ch.state["approvals"]["intent"]).status,
                         approvals.INVALID)


class AT15_UnauthorizedDeploy(SandboxCase):
    def test(self):
        from core import evals
        ok, detail = evals.s_deploy_without_approval(self.sb)
        self.assertTrue(ok, detail)
        ch = self.sb.project.load("CHG-DEMO-001")
        p = self.cli("release", ch.id)
        self.assertEqual(p.returncode, 0)
        self.assertIn("배포 명령은 실행하지 않음", p.stdout)
        self.assertIn("외부 승인 시스템에서만", ch.path("review").read_text())


class AT16_HookBypassDocumented(SandboxCase):
    def test_hook_is_soft_ci_catches(self):
        ch = self.sb.demo()
        ch, _ = fx.advance(self.sb, ch, until="BASELINE_APPROVED")
        target = ch.path("test_spec")
        hook = SCRIPTS / "hooks" / "guard_paths.py"

        def run_hook(payload):
            return subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                                  capture_output=True, text=True).returncode

        self.assertEqual(run_hook({"tool_name": "Write", "tool_input": {"file_path": str(target)}}), 2)
        self.assertEqual(run_hook({"tool_name": "Bash", "tool_input": {"command": f"sed -i '' s/30/31/ {target}"},
                                   "cwd": str(self.sb.root)}), 2)
        # 알려진 우회: 경로를 조립하는 스크립트는 훅이 못 본다 → CI(validate) 가 잡아야 한다
        self.assertEqual(run_hook({"tool_name": "Bash", "tool_input": {"command": "python3 rewrite.py"}}), 0)
        target.write_text(target.read_text().replace("확정 30명", "확정 31명"))
        p = self.cli("ci")
        self.assertEqual(p.returncode, 1)
        self.assertIn("ORACLE_TAMPERED", p.stdout)
        doc = (fx.HARNESS_ROOT / "docs" / "security-limitations.md").read_text()
        self.assertIn("우회", doc)
        self.assertIn("CI", doc)


if __name__ == "__main__":
    unittest.main()
