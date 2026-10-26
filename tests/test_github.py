"""M2: GitHub PR 리뷰 승인 검증 · 고위험 추가 승인 · CI 체크 연동."""
import json
import os

from _base import SandboxCase, fx
from core import github, runner
from fakegh import FakeGh
from validators import approvals, gate as g


class GhCase(SandboxCase):
    def setUp(self):
        super().setUp()
        os.environ["SDLC_GITHUB_REPO"] = "acme/app"
        self.gh = FakeGh(self.sb.root)
        github.set_client(self.gh)
        self.ch = self.sb.demo()

    def gh_approve(self, scope, **review):
        ch = self.sb.reload(self.ch)
        url = self.gh.review(rid=100 + len(self.gh.routes), **review)
        ch.state["approvals"][scope] = g.make_github_record(ch, scope, url)
        ch.save()
        return self.sb.reload(ch)

    def verify(self, scope):
        ch = self.sb.reload(self.ch)
        return approvals.verify(self.sb.root, ch.id, ch.state["approvals"][scope])


class ReviewVerifierTest(GhCase):
    def test_valid_review_is_e2(self):
        self.gh_approve("intent")
        vr = self.verify("intent")
        self.assertEqual((vr.status, vr.level, vr.actor), (approvals.VERIFIED, "E2", "qa-lead"))

    def test_not_approved_state(self):
        self.gh_approve("intent", state="COMMENTED")
        self.assertEqual(self.verify("intent").status, approvals.INVALID)

    def test_self_approval(self):
        self.gh_approve("intent", reviewer="dev", author="dev")
        self.assertIn("자기 승인", self.verify("intent").reason)

    def test_read_only_reviewer(self):
        self.gh_approve("intent", perm="read")
        self.assertEqual(self.verify("intent").status, approvals.INVALID)

    def test_reviewed_content_differs(self):
        self.gh_approve("intent")
        self.gh.content_override[".sdlc/changes/CHG-DEMO-001/intent.md"] = "0" * 40
        vr = self.verify("intent")
        self.assertEqual(vr.status, approvals.INVALID)
        self.assertIn("리뷰 이후 바뀐 내용", vr.reason)

    def test_wrong_repo(self):
        ch = self.sb.reload(self.ch)
        ch.state["approvals"]["intent"] = g.make_github_record(
            ch, "intent", "https://github.com/other/repo/pull/1#pullrequestreview-2")
        ch.save()
        self.assertIn("≠ 이 프로젝트", self.verify("intent").reason)

    def test_policy_roster(self):
        pol = self.sb.root / ".sdlc" / "policies" / "approvers.json"
        pol.parent.mkdir(parents=True)
        pol.write_text(json.dumps({"scopes": {"intent": ["po-kim"]}}))
        self.gh_approve("intent", reviewer="qa-lead")
        self.assertIn("정책상", self.verify("intent").reason)
        self.gh_approve("intent", reviewer="po-kim")
        self.assertEqual(self.verify("intent").status, approvals.VERIFIED)

    def test_network_failure_is_unverifiable(self):
        url = self.gh.review()
        self.gh.routes[url.split("github.com/")[0]] = None
        self.gh.routes["repos/acme/app/pulls/7/reviews/99"] = github.GhUnavailable("offline")
        ch = self.sb.reload(self.ch)
        ch.state["approvals"]["intent"] = g.make_github_record(ch, "intent", url)
        ch.save()
        self.assertEqual(self.verify("intent").status, approvals.UNVERIFIABLE)
        self.assertEqual(g.gate(self.sb.reload(ch), "INTENT_APPROVED").decision, g.MANUAL)

    def test_missing_review_is_invalid(self):
        url = "https://github.com/acme/app/pull/7#pullrequestreview-404"
        ch = self.sb.reload(self.ch)
        ch.state["approvals"]["intent"] = g.make_github_record(ch, "intent", url)
        ch.save()
        self.assertEqual(self.verify("intent").status, approvals.INVALID)


class GateWithGithubTest(GhCase):
    def advance_github(self, until, high=False, security_reviewer=None):
        ch = self.sb.reload(self.ch)
        if high:
            ch.state["risk_level"] = "high"
            ch.save()
        for target in fx.PATH_TO:
            if target in fx.SCOPE_AT:
                ch = self.gh_approve(fx.SCOPE_AT[target])
            if target == "BASELINE_APPROVED" and security_reviewer:
                ch = self.gh_approve("security", reviewer=security_reviewer)
            res = g.gate(ch, target)
            if res.decision != g.ALLOW or target == until:
                return ch, res
            g.apply(ch, res)
            ch = self.sb.reload(ch)
        return ch, res

    def test_standard_flow_with_qc_tests_tree(self):
        _, res = self.advance_github("BASELINE_APPROVED")
        self.assertEqual(res.decision, g.ALLOW, res.to_dict())

    def test_high_risk_requires_security_policy(self):
        _, res = self.advance_github("BASELINE_APPROVED", high=True)
        self.assertEqual(res.decision, g.MANUAL)
        self.assertTrue(any("security" in m for m in res.manual))

    def test_high_risk_security_distinct_reviewer(self):
        pol = self.sb.root / ".sdlc" / "policies" / "approvers.json"
        pol.parent.mkdir(parents=True)
        pol.write_text(json.dumps({"scopes": {"security": ["sec-lee", "qa-lead"]}}))
        _, res = self.advance_github("BASELINE_APPROVED", high=True, security_reviewer="qa-lead")
        self.assertIn("SECURITY_SAME_REVIEWER", self.codes(res.reasons))
        ch = self.gh_approve("security", reviewer="sec-lee")
        res = g.gate(ch, "BASELINE_APPROVED")
        self.assertEqual(res.decision, g.ALLOW, res.to_dict())

    def test_local_approval_still_rejected_for_high(self):
        ch = self.sb.reload(self.ch)
        ch.state["risk_level"] = "high"
        ch.save()
        fx.approve(ch, "intent")
        self.assertEqual(g.gate(self.sb.reload(ch), "INTENT_APPROVED").decision, g.MANUAL)


class ReleaseCiTest(GhCase):
    def setUp(self):
        super().setUp()
        github.set_client(None)
        os.environ["SDLC_GITHUB_OFFLINE"] = "1"
        ch, _ = fx.advance(self.sb, self.ch)
        runner.run(ch)
        ch = self.sb.reload(ch)
        for t in ("QC_PASSED", "REVIEW_PENDING"):
            g.apply(ch, g.gate(ch, t))
            ch = self.sb.reload(ch)
        github.set_client(self.gh)
        self.head = fx.git(self.sb.root, "rev-parse", "HEAD").strip()
        self.ch = self.gh_approve("release", reviewer="ops-park", commit=self.head)

    def checks(self, *runs):
        self.gh.routes[f"repos/acme/app/commits/{self.head}/check-runs?per_page=100"] = {"check_runs": list(runs)}

    def test_release_allowed_with_review_and_ci(self):
        self.checks({"name": "validate", "status": "completed", "conclusion": "success"})
        res = g.gate(self.sb.reload(self.ch), "RELEASE_APPROVED")
        self.assertEqual(res.decision, g.ALLOW, res.to_dict())

    def test_ci_failure_blocks(self):
        self.checks({"name": "validate", "status": "completed", "conclusion": "failure"})
        self.assertIn("CI_CHECK_FAILED", self.codes(g.gate(self.sb.reload(self.ch), "RELEASE_APPROVED").reasons))

    def test_latest_ci_run_wins(self):
        self.checks({"id": 1, "name": "validate", "status": "completed", "conclusion": "failure"},
                    {"id": 2, "name": "validate", "status": "completed", "conclusion": "success"})
        self.assertEqual(g.gate(self.sb.reload(self.ch), "RELEASE_APPROVED").decision, g.ALLOW)

    def test_ci_missing_or_running_is_manual(self):
        self.checks()
        self.assertEqual(g.gate(self.sb.reload(self.ch), "RELEASE_APPROVED").decision, g.MANUAL)
        self.checks({"name": "validate", "status": "in_progress", "conclusion": None})
        self.assertEqual(g.gate(self.sb.reload(self.ch), "RELEASE_APPROVED").decision, g.MANUAL)

    def test_review_on_other_commit_invalid(self):
        self.ch = self.gh_approve("release", reviewer="ops-park", commit="d" * 40)
        self.checks({"name": "validate", "status": "completed", "conclusion": "success"})
        res = g.gate(self.sb.reload(self.ch), "RELEASE_APPROVED")
        self.assertIn("APPROVAL_INVALID", self.codes(res.reasons))
