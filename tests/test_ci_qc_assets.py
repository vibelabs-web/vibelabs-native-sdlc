"""CI 의 잠긴 QC 자산 승인 검사 (scripts/ci/check_qc_assets.py) — 임시 리포 + 가짜 gh."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _base import HARNESS

SCRIPT = HARNESS / "scripts" / "ci" / "check_qc_assets.py"
BOT = "gk[bot]"


def sh(cwd, *a):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class CheckQcAssetsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.remote = self.tmp / "remote.git"
        sh(self.tmp, "git", "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.repo = self.tmp / "repo"
        sh(self.tmp, "git", "clone", "-q", str(self.remote), str(self.repo))
        for k, v in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false")):
            sh(self.repo, "git", "config", k, v)
        (self.repo / "README.md").write_text("x\n")
        self.commit("base")
        sh(self.repo, "git", "push", "-q", "origin", "HEAD:main")
        sh(self.repo, "git", "checkout", "-q", "-b", "feature")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.reviews = []

    def commit(self, msg):
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-q", "-m", msg)
        return sh(self.repo, "git", "rev-parse", "HEAD")

    def set_policy_on_main(self, plan_test):
        sh(self.repo, "git", "checkout", "-q", "main")
        p = self.repo / ".sdlc" / "policies" / "approvers.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"scopes": {"plan_test": plan_test}}))
        self.commit("policy")
        sh(self.repo, "git", "push", "-q", "origin", "main")
        sh(self.repo, "git", "checkout", "-q", "feature")
        sh(self.repo, "git", "rebase", "-q", "main")

    def add_qc_asset(self, text="TC"):
        p = self.repo / ".sdlc" / "changes" / "CHG-DEMO-001" / "test-spec.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return self.commit("qc asset")

    def run_check(self, labels=(), base="main"):
        gh = self.bin / "gh"
        gh.write_text(f"#!/bin/sh\ncat <<'JSON'\n{json.dumps(self.reviews)}\nJSON\n")
        gh.chmod(0o755)
        sh(self.repo, "git", "fetch", "-q", "origin")
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "BASE_REF": base, "PR_NUMBER": "1",
               "REPO": "acme/app", "LABELS": json.dumps(list(labels)), "GH_TOKEN": "x"}
        return subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo, capture_output=True, text=True, env=env)

    def test_empty_base_ref_is_explicit_error(self):
        """회귀: pull_request_review 이벤트에서 github.base_ref 가 비어 `origin/...HEAD` 로 깨지던 문제."""
        self.add_qc_asset()
        r = self.run_check(base="")
        self.assertEqual(r.returncode, 2)
        self.assertIn("BASE_REF", r.stdout)

    def test_workflow_uses_event_base_ref(self):
        wf = (HARNESS / ".github" / "workflows" / "sdlc-validate.yml").read_text()
        self.assertIn("github.event.pull_request.base.ref", wf)
        self.assertNotIn("BASE_REF: ${{ github.base_ref }}", wf)

    def test_no_qc_change_passes(self):
        (self.repo / "app.py").write_text("x=1\n")
        self.commit("code")
        self.assertEqual(self.run_check().returncode, 0)

    def test_label_passes(self):
        self.add_qc_asset()
        self.assertEqual(self.run_check(labels=["qc-oracle-approved"]).returncode, 0)

    def test_no_policy_on_base_fails(self):
        self.add_qc_asset()
        self.assertEqual(self.run_check().returncode, 1)

    def test_policy_added_in_pr_itself_does_not_count(self):
        p = self.repo / ".sdlc" / "policies" / "approvers.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"scopes": {"plan_test": [BOT]}}))
        sha = self.add_qc_asset()
        self.reviews = [{"state": "APPROVED", "user": {"login": BOT}, "commit_id": sha}]
        self.assertEqual(self.run_check().returncode, 1, "PR 이 스스로 넣은 정책으로 자기 승인 불가")

    def test_bot_review_from_base_policy_passes(self):
        self.set_policy_on_main([BOT])
        sha = self.add_qc_asset()
        self.reviews = [{"state": "APPROVED", "user": {"login": BOT}, "commit_id": sha}]
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_asset_changed_after_review_fails(self):
        self.set_policy_on_main([BOT])
        sha = self.add_qc_asset("v1")
        self.add_qc_asset("v2 — 승인 후 기대값 변경")
        self.reviews = [{"state": "APPROVED", "user": {"login": BOT}, "commit_id": sha}]
        self.assertEqual(self.run_check().returncode, 1)

    def test_unlisted_reviewer_fails(self):
        self.set_policy_on_main([BOT])
        sha = self.add_qc_asset()
        self.reviews = [{"state": "APPROVED", "user": {"login": "random-user"}, "commit_id": sha}]
        self.assertEqual(self.run_check().returncode, 1)


if __name__ == "__main__":
    unittest.main()
