"""상태 전이·증거 무결성·결함 규칙·보고서 (A1·A3 보강)."""
import json
import os
import unittest

from _base import SandboxCase, fx
from core import bugs, lifecycle, report, runner
from core.util import SdlcError, read_json
from validators import check, evidence, gate as g


class StructureTest(SandboxCase):
    def test_duplicate_orphan_and_reuse(self):
        ch = self.sb.demo()
        p = ch.path("plan")
        text = p.read_text()
        p.write_text(text.replace("| TASK-003 | REQ-003 |", "| TASK-002 | REQ-003 |")
                     + "\n| TASK-ID | REQ-ID | 변경 파일/컴포넌트 |\n|---|---|---|\n| TASK-009 | - | app/x.py |\n")
        codes = self.codes(check.validate(ch).errors)
        self.assertIn("DUPLICATE_ID", codes)
        self.assertIn("ORPHAN_TASK", codes)
        ch.state["retired_ids"] = ["TC-001"]
        ch.save()
        self.assertIn("ID_REUSED", self.codes(check.validate(self.sb.reload(ch)).errors))

    def test_manifest_path_escape(self):
        ch = self.sb.demo()
        m = read_json(ch.path("qc_manifest"))
        m["cases"][0]["cwd"] = "../../outside"
        ch.path("qc_manifest").write_text(json.dumps(m))
        self.assertIn("MANIFEST_PATH", self.codes(check.validate(ch).errors))

    def test_state_schema(self):
        ch = self.sb.demo()
        ch.state["stage"] = "SHIPPED"
        ch.save()
        self.assertIn("STATE_SCHEMA", self.codes(check.validate(self.sb.reload(ch)).errors))

    def test_validate_json_exit_codes(self):
        ch = self.sb.demo()
        code, data = self.cli_json("validate", ch.id)
        self.assertEqual(code, 0)
        self.assertTrue(data["ok"])
        ch.path("spec").write_text("# 메타 없음\n")
        code, data = self.cli_json("validate", "--all")
        self.assertEqual(code, 1)
        self.assertIn("FRONTMATTER_MISSING", {i["code"] for i in data["changes"][0]["issues"]})


class GateFlowTest(SandboxCase):
    def test_qc_running_requires_commit_and_self_check(self):
        ch = self.sb.demo()
        ch, _ = fx.advance(self.sb, ch, until="BUILDING")
        res = g.gate(ch, "QC_RUNNING")
        self.assertIn("NO_BUILD_CHECK", self.codes(res.reasons))
        (self.sb.root / "app" / "registration.py").write_text("# 미커밋\n")
        lifecycle.build_check(ch, fx.self_check_cmd())
        res = g.gate(self.sb.reload(ch), "QC_RUNNING")
        self.assertIn("DIRTY_WORKTREE", self.codes(res.reasons))

    def test_qc_run_refuses_wrong_stage_and_dirty(self):
        ch = self.sb.demo()
        with self.assertRaises(SdlcError):
            runner.run(ch)
        ch, _ = fx.advance(self.sb, ch)
        (self.sb.root / "app" / "scratch.py").write_text("x = 1\n")
        with self.assertRaises(SdlcError):
            runner.run(ch)

    def test_dirty_evidence_is_unusable(self):
        ch = self.sb.demo()
        ch, _ = fx.advance(self.sb, ch)
        (self.sb.root / "app" / "scratch.py").write_text("x = 1\n")
        runner.run(ch, allow_dirty=True)
        os.remove(self.sb.root / "app" / "scratch.py")
        res = g.gate(self.sb.reload(ch), "QC_PASSED")
        self.assertIn("EVIDENCE_DIRTY", self.codes(res.reasons))

    def test_isolated_worktree_run(self):
        ch = self.sb.demo()
        ch, _ = fx.advance(self.sb, ch)
        r = runner.run(ch, isolated=True)
        self.assertTrue(r["run"]["environment"].startswith("isolated-worktree"))
        self.assertEqual(g.gate(self.sb.reload(ch), "QC_PASSED").decision, g.ALLOW)


class EvidenceIntegrityTest(SandboxCase):
    def setUp(self):
        super().setUp()
        ch = self.sb.demo()
        ch, _ = fx.advance(self.sb, ch)
        runner.run(ch)
        self.ch = self.sb.reload(ch)
        self.run_path = evidence.run_path(self.ch, "RUN-001")

    def test_edited_run_json(self):
        run = read_json(self.run_path)
        run["cases"][2]["result"] = "FAIL"
        self.run_path.write_text(json.dumps(run))
        self.assertIn("EVIDENCE_TAMPERED", self.codes(evidence.verify(self.ch, run, run["commit_sha"])))

    def test_edited_log(self):
        log = self.ch.dir / "evidence" / "RUN-001" / "TC-001.log"
        log.write_text("fake OK")
        run = read_json(self.run_path)
        self.assertIn("EVIDENCE_LOG_MISMATCH", self.codes(evidence.verify(self.ch, run, run["commit_sha"])))

    def test_no_commit_evidence(self):
        run = read_json(self.run_path)
        run["commit_sha"] = None
        run["report_sha256"] = evidence.report_digest(run)
        self.assertIn("EVIDENCE_NO_COMMIT", self.codes(evidence.verify(self.ch, run, None)))

    def test_report_coverage(self):
        data = report.build(self.ch)
        self.assertEqual(data["verified_coverage"], 1.0)
        self.assertEqual(data["trace_coverage"], 1.0)
        report.write_markdown(self.ch, data)
        self.assertIn("| REQ-001 |", self.ch.path("traceability").read_text())
        self.assertIn("- PASS", self.ch.path("qc_report").read_text())


class BugRulesTest(SandboxCase):
    def test_role_rules(self):
        ch = self.sb.demo(impl="registration_no_promotion")
        ch, _ = fx.advance(self.sb, ch)
        runner.run(ch)
        ch = self.sb.reload(ch)
        b = bugs.load_all(ch)[0]
        with self.assertRaises(SdlcError):
            bugs.transition(ch, b, "closed", role="builder")
        bugs.transition(ch, b, "triaged", role="qc-verifier")
        bugs.transition(ch, b, "in_progress", role="builder")
        with self.assertRaises(SdlcError):
            bugs.transition(ch, b, "ready_for_retest", role="qc-verifier")
        self.assertEqual(bugs.validate(ch), [])

    def test_same_sha_retest_does_not_verify(self):
        ch = self.sb.demo(impl="registration_no_promotion")
        ch, _ = fx.advance(self.sb, ch)
        runner.run(ch)
        ch = self.sb.reload(ch)
        b = bugs.load_all(ch)[0]
        for to in ("triaged", "in_progress", "ready_for_retest"):
            bugs.transition(ch, b, to, role="builder")
        ch.save()
        r = runner.run(self.sb.reload(ch))
        self.assertTrue(any("같은 SHA" in e for e in r["bug_events"]))
        self.assertEqual(bugs.load_all(self.sb.reload(ch))[0].status, "ready_for_retest")


class InvalidationTest(SandboxCase):
    def test_spec_change_after_qc_invalidates_evidence(self):
        ch = self.sb.demo()
        ch, _ = fx.advance(self.sb, ch)
        runner.run(ch)
        ch = self.sb.reload(ch)
        sp = ch.path("spec")
        sp.write_text(sp.read_text() + "\n- 정책 메모\n")
        res = g.gate(ch, "QC_PASSED")
        self.assertEqual(res.decision, g.BLOCK)
        self.assertIn("BASELINE_DRIFT", self.codes(res.reasons))
        lifecycle.reopen(ch, "SPEC_DRAFT", "정책 메모 추가")
        ch = self.sb.reload(ch)
        self.assertIsNone(ch.state["last_verification_run"])
        self.assertIn("RUN-001", ch.state["stale_runs"])
        self.assertNotIn("spec", ch.state["approvals"])
        self.assertIn("intent", ch.state["approvals"])


if __name__ == "__main__":
    unittest.main()
