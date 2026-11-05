"""QC 시간 단축: 재검증 범위·병렬·setup·등급별 깊이·소요 시간 기록."""
import json

from _base import SandboxCase, fx

from core import bugs, report, runner
from core.util import SdlcError
from validators import check, evidence, gate as g


class QcSpeedCase(SandboxCase):
    def demo(self, impl=None, edit=None, risk=None):
        ch = self.sb.demo(impl)
        if risk:
            ch.state["risk_level"] = risk
            ch.save()
        if edit:
            path = ch.path("qc_manifest")
            man = json.loads(path.read_text(encoding="utf-8"))
            edit(man)
            path.write_text(json.dumps(man), encoding="utf-8")
        self.sb.commit("setup")
        return self.sb.reload(ch)

    def to_defect_fixed(self, edit=None):
        """TC-002·003 실패 → DEFECT_OPEN → 수정 커밋 → 재검증 준비까지."""
        ch = self.demo("registration_no_promotion", edit)
        ch, blocked = fx.advance(self.sb, ch)
        self.assertIsNone(blocked)
        first = runner.run(ch, isolated=True)
        self.assertTrue(first["bug_events"])
        ch = self.sb.reload(ch)
        g.apply(ch, g.gate(ch, "DEFECT_OPEN"))
        ch = self.sb.reload(ch)
        ch, _ = fx.to_building_again(self.sb, ch)
        self.sb.use_impl("correct")
        self.sb.commit("fix")
        ch = self.sb.reload(ch)
        for b in bugs.load_all(ch):
            for to in ("triaged", "in_progress", "ready_for_retest"):
                bugs.transition(ch, b, to, role="builder")
        ch.save()
        self.sb.commit("ready")
        ch = self.sb.reload(ch)
        ch, res = fx.to_qc_running(self.sb, ch)
        self.assertEqual(res.decision, g.ALLOW, res.reasons)
        return ch, first["run"]["run_id"]


class RetestTest(QcSpeedCase):
    def test_retest_runs_only_defect_tcs_and_cannot_pass_gate(self):
        ch, first_run = self.to_defect_fixed()
        out = runner.run(ch, isolated=True, retest=True)
        ch = self.sb.reload(ch)
        ran = {c["tc_id"] for c in out["run"]["cases"]}
        self.assertIn("TC-003", ran)
        self.assertNotIn("TC-001", ran)
        self.assertEqual(out["run"]["scope"], "retest")
        self.assertEqual(ch.state["last_verification_run"], first_run)  # 게이트 증거 불변
        self.assertTrue(all(c["result"] == "PASS" for c in out["run"]["cases"]))
        self.assertEqual(g.gate(ch, "QC_PASSED").decision, g.BLOCK)

        full = runner.run(ch, isolated=True)
        ch = self.sb.reload(ch)
        self.assertEqual(full["run"]["scope"], "full")
        self.assertEqual(g.gate(ch, "QC_PASSED").decision, g.ALLOW)

    def test_retest_includes_same_regression_group(self):
        def group(man):
            for c in man["cases"]:
                if c["tc_id"] in ("TC-001", "TC-003"):
                    c["regression_group"] = "core"
        ch, _ = self.to_defect_fixed(group)
        out = runner.run(ch, isolated=True, retest=True)
        self.assertIn("TC-001", {c["tc_id"] for c in out["run"]["cases"]})

    def test_retest_refused_without_open_bug(self):
        ch = self.demo()
        ch, _ = fx.advance(self.sb, ch)
        with self.assertRaises(SdlcError):
            runner.run(ch, isolated=True, retest=True)

    def test_partial_run_rejected_even_if_state_points_at_it(self):
        ch, _ = self.to_defect_fixed()
        out = runner.run(ch, isolated=True, retest=True)
        ch = self.sb.reload(ch)
        ch.state["last_verification_run"] = out["run"]["run_id"]
        ch.save()
        res = g.gate(self.sb.reload(ch), "QC_PASSED")
        self.assertIn("EVIDENCE_PARTIAL", self.codes(res.reasons))


class ParallelSetupTest(QcSpeedCase):
    SLEEP = ["python3", "-c", "import time; time.sleep(0.5); print('ok')"]

    def test_parallel_is_faster_keeps_order_and_valid_evidence(self):
        def sleepy(n):
            def edit(man):
                man["max_parallel"] = n
                for c in man["cases"]:
                    c["cmd"], c["cwd"] = self.SLEEP, "."
            return edit
        ch = self.demo(edit=sleepy(4))
        ch, _ = fx.advance(self.sb, ch)
        out = runner.run(ch, isolated=True)["run"]
        order = [c["tc_id"] for c in out["cases"]]
        self.assertEqual(order, ["TC-001", "TC-002", "TC-003", "TC-004"])
        self.assertLess(out["duration_ms"], 1500)  # 순차면 2000ms 이상
        self.assertTrue(all(c["duration_ms"] >= 400 for c in out["cases"]))
        ch = self.sb.reload(ch)
        self.assertEqual(evidence.verify(ch, out, fx.git(self.sb.root, "rev-parse", "HEAD").strip()), [])

    def test_setup_runs_once_before_cases(self):
        code = "import pathlib; p=pathlib.Path('setup.count'); p.write_text(p.read_text()+'x' if p.exists() else 'x')"
        check_cmd = ["python3", "-c", "import pathlib,sys; sys.exit(0 if pathlib.Path('setup.count').read_text()=='x' else 1)"]

        def edit(man):
            man["setup"] = [{"cmd": ["python3", "-c", code]}]
            for c in man["cases"]:
                c["cmd"], c["cwd"] = check_cmd, "."
        ch = self.demo(edit=edit)
        ch, _ = fx.advance(self.sb, ch)
        out = runner.run(ch, isolated=True)["run"]
        self.assertEqual({c["result"] for c in out["cases"]}, {"PASS"})
        self.assertEqual(len(out["setup"]), 1)

    def test_setup_failure_blocks_all_without_bugs(self):
        def edit(man):
            man["setup"] = [{"cmd": ["python3", "-c", "raise SystemExit(3)"]}]
        ch = self.demo(edit=edit)
        ch, _ = fx.advance(self.sb, ch)
        result = runner.run(ch, isolated=True)
        self.assertEqual({c["result"] for c in result["run"]["cases"]}, {"BLOCKED"})
        self.assertEqual(result["bug_events"], [])
        self.assertEqual(g.gate(self.sb.reload(ch), "QC_PASSED").decision, g.BLOCK)

    def test_tampered_setup_log_invalidates_run(self):
        def edit(man):
            man["setup"] = [{"cmd": ["python3", "-c", "print('hi')"]}]
        ch = self.demo(edit=edit)
        ch, _ = fx.advance(self.sb, ch)
        out = runner.run(ch, isolated=True)["run"]
        ch = self.sb.reload(ch)
        (ch.dir / out["setup"][0]["log_path"]).write_text("forged")
        head = fx.git(self.sb.root, "rev-parse", "HEAD").strip()
        self.assertIn("EVIDENCE_LOG_MISMATCH", self.codes(evidence.verify(ch, out, head)))


class RiskDepthTest(QcSpeedCase):

    def test_lite_skips_non_must_tc(self):
        ch = self.demo(risk="lite")
        rep_index = {"tcs": {"TC-001": {"reqs": ["REQ-001"]}, "TC-002": {"reqs": ["REQ-002"]},
                             "TC-003": {"reqs": ["REQ-003"]}, "TC-004": {"reqs": ["REQ-OPT"]}},
                     "reqs": {"REQ-001": {"must": True}, "REQ-002": {"must": True},
                              "REQ-003": {"must": True}, "REQ-OPT": {"must": False}}}

        class Rep:
            index = rep_index
        man = json.loads(ch.path("qc_manifest").read_text(encoding="utf-8"))
        chosen, skipped = runner._select_cases(ch, man, Rep, retest=False)
        self.assertEqual([c["tc_id"] for c in chosen], ["TC-001", "TC-002", "TC-003"])
        self.assertEqual(list(skipped), ["TC-004"])

    def test_standard_runs_non_must_tc(self):
        ch = self.demo()
        man = json.loads(ch.path("qc_manifest").read_text(encoding="utf-8"))

        class Rep:
            index = {"tcs": {"TC-004": {"reqs": ["REQ-OPT"]}}, "reqs": {"REQ-OPT": {"must": False}}}
        chosen, skipped = runner._select_cases(ch, man, Rep, retest=False)
        self.assertEqual(len(chosen), 4)
        self.assertEqual(skipped, {})

    def test_lite_run_passes_gate(self):
        ch = self.demo(risk="lite")
        ch, blocked = fx.advance(self.sb, ch)
        self.assertIsNone(blocked)
        runner.run(ch, isolated=True)
        self.assertEqual(g.gate(self.sb.reload(ch), "QC_PASSED").decision, g.ALLOW)

    def test_tc_budget_warns_without_blocking(self):
        ch = self.demo(risk="lite")  # REQ-001 에 TC-001·TC-004 → lite 기준 1 초과
        ch, blocked = fx.advance(self.sb, ch)
        self.assertIsNone(blocked)
        rep = check.validate(ch)
        hit = [i for i in rep.issues if i.code == "QC_TC_OVER_BUDGET"]
        self.assertTrue(hit)
        self.assertEqual(hit[0].severity, "warning")


class TimingCompatTest(QcSpeedCase):
    def test_report_shows_durations(self):
        ch = self.demo()
        ch, _ = fx.advance(self.sb, ch)
        runner.run(ch, isolated=True)
        ch = self.sb.reload(ch)
        data = report.build(ch)
        self.assertEqual(data["timing"]["runs"][0]["scope"], "full")
        self.assertIsNotNone(data["timing"]["runs"][0]["ms"])
        self.assertTrue(data["timing"]["slowest"])
        report.write_markdown(ch, data)
        self.assertIn("## Timing", ch.path("qc_report").read_text(encoding="utf-8"))

    def test_old_run_without_new_fields_still_valid(self):
        ch = self.demo()
        ch, _ = fx.advance(self.sb, ch)
        run = runner.run(ch, isolated=True)["run"]
        for k in ("scope", "duration_ms", "setup", "report_sha256"):
            run.pop(k)
        for c in run["cases"]:
            c.pop("duration_ms")
        run["report_sha256"] = evidence.report_digest(run)
        ch = self.sb.reload(ch)
        evidence.run_path(ch, run["run_id"]).write_text(json.dumps(run), encoding="utf-8")
        self.assertEqual(g.gate(self.sb.reload(ch), "QC_PASSED").decision, g.ALLOW)
        data = report.build(self.sb.reload(ch))
        self.assertIsNone(data["timing"]["runs"][0]["ms"])
        report.write_markdown(self.sb.reload(ch), data)
