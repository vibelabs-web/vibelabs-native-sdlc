"""완전 자율 승인: GitHub App 봇 신원 + 규칙 기반 auto-approve."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from _base import SandboxCase, fx
from core import autoapprove, github, github_app, lifecycle, runner
from fakegh import FakeGh
from validators import approvals, gate as g

BOT = "gk[bot]"


class JwtTest(unittest.TestCase):
    def test_rs256_signature_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            key, pub = Path(d) / "k.pem", Path(d) / "p.pem"
            subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], capture_output=True, check=True)
            subprocess.run(["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(pub)], capture_output=True, check=True)
            jwt = github_app.make_jwt(123, key, now=1_800_000_000)
            h, p, sig = jwt.split(".")
            payload = json.loads(github_app.base64.urlsafe_b64decode(p + "=="))
            self.assertEqual(payload["iss"], "123")
            self.assertLess(payload["exp"] - payload["iat"], 660)
            sigf = Path(d) / "s.bin"
            sigf.write_bytes(github_app.base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)))
            v = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sigf)],
                               input=f"{h}.{p}".encode(), capture_output=True)
            self.assertEqual(v.returncode, 0, v.stdout)

    def test_manifest_permissions_minimal(self):
        m = github_app.manifest("acme/app", "http://127.0.0.1:1/callback", "gk")
        self.assertEqual(m["default_permissions"]["pull_requests"], "write")
        self.assertEqual(m["default_permissions"]["contents"], "read")
        self.assertFalse(m["public"])


class AutonomyCase(SandboxCase):
    def setUp(self):
        super().setUp()
        os.environ["SDLC_GITHUB_REPO"] = "acme/app"
        self.gh = FakeGh(self.sb.root)
        self.gh.bot_login = BOT
        self.gh.open_pr(7)
        github.set_client(self.gh)
        github_app.set_app_client(self.gh)
        self.ch = self.sb.demo()

    def tearDown(self):
        github_app.set_app_client(None)
        super().tearDown()

    def policy(self, scopes=None, distinct=False):
        pol = self.sb.root / ".sdlc" / "policies" / "approvers.json"
        pol.parent.mkdir(parents=True, exist_ok=True)
        allowed = {s: [BOT] for s in (scopes or ["intent", "spec", "plan_test", "security", "release"])}
        pol.write_text(json.dumps({"scopes": allowed, "require_distinct_security_reviewer": distinct}))
        self.sb.commit("policy")

    def auto(self, scope):
        return autoapprove.auto_approve(self.sb.reload(self.ch), scope, 7)

    def step(self, target):
        ch = self.sb.reload(self.ch)
        res = g.gate(ch, target)
        self.assertEqual(res.decision, g.ALLOW, res.to_dict())
        g.apply(ch, res)


class BotVerifierTest(AutonomyCase):
    def test_bot_needs_policy_entry(self):
        with self.assertRaises(autoapprove.Refused) as cm:
            self.auto("intent")
        self.assertIn("봇", str(cm.exception))
        self.policy(["intent"])
        out = self.auto("intent")
        self.assertEqual((out["approver"], out["level"]), (BOT, "E2"))
        self.step("INTENT_APPROVED")


class AutoApproveRulesTest(AutonomyCase):
    def setUp(self):
        super().setUp()
        self.policy()

    def posted_reviews(self):
        return [c for c in self.gh.calls if c[0] == "POST" and c[1].endswith("/reviews")]

    def test_blocker_means_no_review(self):
        p = self.ch.path("intent")
        p.write_text(p.read_text() + "\n## 메모\n- <채울 것>\n")
        self.sb.commit("placeholder")
        with self.assertRaises(autoapprove.Refused):
            self.auto("intent")
        self.assertEqual(self.posted_reviews(), [], "차단 사유가 있으면 봇은 리뷰를 남기지 않는다")

    def test_unpushed_head_refused(self):
        self.gh.routes["repos/acme/app/pulls/7"] = {"state": "open", "user": {"login": "x"},
                                                    "head": {"sha": "f" * 40}}
        with self.assertRaises(autoapprove.Refused) as cm:
            self.auto("intent")
        self.assertIn("push", str(cm.exception))

    def test_closed_pr_refused(self):
        self.gh.routes["repos/acme/app/pulls/7"] = {"state": "closed", "head": {"sha": "f" * 40}}
        with self.assertRaises(autoapprove.Refused):
            self.auto("intent")

    def test_ci_not_done_is_manual_refusal_at_release(self):
        ch, _ = fx.advance(self.sb, self.ch)  # 로컬 E1 승인으로 빠르게 진행 (standard)
        runner.run(ch)
        self.step("QC_PASSED")
        self.step("REVIEW_PENDING")
        with self.assertRaises(autoapprove.Refused) as cm:
            self.auto("release")
        self.assertTrue(cm.exception.manual)
        self.assertIn("CI", str(cm.exception))


class FullAutonomyHighRiskTest(AutonomyCase):
    def test_high_risk_end_to_end_without_human(self):
        self.policy()
        ch = self.sb.reload(self.ch)
        ch.state["risk_level"] = "high"
        ch.save()
        self.auto("intent"); self.step("INTENT_APPROVED")
        self.step("SPEC_DRAFT")
        self.auto("spec"); self.step("SPEC_APPROVED")
        self.step("PLAN_TEST_DRAFT")
        self.auto("plan_test"); self.auto("security"); self.step("BASELINE_APPROVED")
        self.step("BUILDING")
        lifecycle.build_check(self.sb.reload(self.ch), fx.self_check_cmd())
        self.step("QC_RUNNING")
        runner.run(self.sb.reload(self.ch))
        head = fx.git(self.sb.root, "rev-parse", "HEAD").strip()
        self.gh.routes[f"repos/acme/app/commits/{head}/check-runs?per_page=100"] = {
            "check_runs": [{"name": "validate", "status": "completed", "conclusion": "success"}]}
        self.step("QC_PASSED")
        self.step("REVIEW_PENDING")
        self.auto("release")
        self.step("RELEASE_APPROVED")
        ch = self.sb.reload(self.ch)
        self.assertEqual(ch.state["stage"], "RELEASE_APPROVED")
        self.assertTrue(all(v["kind"] == "github_review" for v in ch.state["approvals"].values()))

    def test_distinct_security_still_enforced_when_policy_says_so(self):
        self.policy(distinct=True)
        ch = self.sb.reload(self.ch)
        ch.state["risk_level"] = "high"
        ch.save()
        self.auto("intent"); self.step("INTENT_APPROVED")
        self.step("SPEC_DRAFT")
        self.auto("spec"); self.step("SPEC_APPROVED")
        self.step("PLAN_TEST_DRAFT")
        self.auto("plan_test"); self.auto("security")
        res = g.gate(self.sb.reload(self.ch), "BASELINE_APPROVED")
        self.assertIn("SECURITY_SAME_REVIEWER", {i.code for i in res.reasons})
