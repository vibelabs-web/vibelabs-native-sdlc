"""CI 의 플러그인 version 상승 검사 (scripts/ci/check_plugin_version.py) — 임시 리포."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _base import HARNESS

SCRIPT = HARNESS / "scripts" / "ci" / "check_plugin_version.py"


def sh(cwd, *a):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class CheckPluginVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        remote = self.tmp / "remote.git"
        sh(self.tmp, "git", "init", "-q", "--bare", "-b", "main", str(remote))
        self.repo = self.tmp / "repo"
        sh(self.tmp, "git", "clone", "-q", str(remote), str(self.repo))
        for k, v in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false")):
            sh(self.repo, "git", "config", k, v)
        self.write("README.md", "x\n")
        self.set_version("0.3.0")
        self.write("skills/sdlc/SKILL.md", "v1\n")
        self.commit()
        sh(self.repo, "git", "push", "-q", "origin", "HEAD:main")
        sh(self.repo, "git", "checkout", "-q", "-b", "feature")

    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def set_version(self, v):
        self.write(".claude-plugin/plugin.json", json.dumps({"name": "p", "version": v}))

    def commit(self):
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-q", "-m", "c")

    def run_check(self):
        env = {**os.environ, "BASE_REF": "main"}
        return subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo, env=env,
                              capture_output=True, text=True)

    def test_docs_only_change_passes_without_bump(self):
        self.write("README.md", "y\n")
        self.commit()
        self.assertEqual(self.run_check().returncode, 0)

    def test_skill_change_without_bump_fails(self):
        self.write("skills/sdlc/SKILL.md", "v2\n")
        self.commit()
        r = self.run_check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("version 을 올려야 함", r.stdout)

    def test_skill_change_with_bump_passes(self):
        self.write("skills/sdlc/SKILL.md", "v2\n")
        self.set_version("0.3.1")
        self.commit()
        self.assertEqual(self.run_check().returncode, 0)

    def test_downgrade_fails(self):
        self.write("scripts/x.py", "1\n")
        self.set_version("0.2.9")
        self.commit()
        self.assertEqual(self.run_check().returncode, 1)

    def test_non_semver_fails(self):
        self.set_version("next")
        self.commit()
        self.assertEqual(self.run_check().returncode, 1)

    def test_package_json_version_must_match(self):
        self.write("bin/x.js", "1\n")
        self.set_version("0.3.1")
        self.write("package.json", json.dumps({"name": "p", "version": "0.3.0"}))
        self.commit()
        r = self.run_check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("같이 올려야 함", r.stdout)

    def test_installer_change_needs_bump(self):
        self.write("package.json", json.dumps({"name": "p", "version": "0.3.0"}))
        self.commit()
        self.assertEqual(self.run_check().returncode, 1)

    def test_empty_base_ref_is_usage_error(self):
        env = {**os.environ, "BASE_REF": ""}
        r = subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
