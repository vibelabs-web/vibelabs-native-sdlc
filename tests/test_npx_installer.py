"""npx 설치기 (bin/vibelabs-sdlc.js) — 임시 ~/.claude 와 가짜 claude 명령으로 검사. node 가 없으면 건너뛴다."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _base import HARNESS

BIN = HARNESS / "bin" / "vibelabs-sdlc.js"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node 없음")
class NpxInstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.claude_dir = self.tmp / "claude"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.calls = self.tmp / "calls.log"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_bin(self, *args, with_claude=False, plugins=(), marketplaces=()):
        path = [str(self.bin)]
        if with_claude:
            self.fake_claude(plugins, marketplaces)
        # python3·git 은 진짜를 쓰되 claude 는 가짜만 보이게 한다
        for tool in ("python3", "git"):
            real = shutil.which(tool)
            link = self.bin / tool
            if real and not link.exists():
                link.symlink_to(real)
        env = {**os.environ, "PATH": os.pathsep.join(path), "VIBELABS_SDLC_CLAUDE_DIR": str(self.claude_dir)}
        return subprocess.run([NODE, str(BIN), *args], env=env, capture_output=True, text=True)

    def fake_claude(self, plugins, marketplaces):
        script = self.bin / "claude"
        script.write_text(
            "#!/bin/sh\n"
            f"echo \"$*\" >> '{self.calls}'\n"
            'case "$*" in\n'
            f"  'plugin marketplace list --json') echo '{json.dumps(list(marketplaces))}' ;;\n"
            f"  'plugin list --json') echo '{json.dumps(list(plugins))}' ;;\n"
            "esac\n"
            "exit 0\n")
        script.chmod(0o755)

    def calls_list(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    # ------------------------------------------------------------ 복사 모드

    def test_copy_install_links_skills_and_agents(self):
        r = self.run_bin("--copy")
        self.assertEqual(r.returncode, 0, r.stderr)
        home = self.claude_dir / "vibelabs-sdlc"
        self.assertTrue((home / "scripts" / "sdlc.py").is_file())
        self.assertFalse((home / "tests").exists())
        link = self.claude_dir / "skills" / "sdlc"
        self.assertEqual(os.readlink(link), str(home / "skills" / "sdlc"))
        self.assertTrue((self.claude_dir / "agents" / "sdlc-builder.md").is_symlink())
        # 스킬이 쓰는 경로 규칙 ${CLAUDE_SKILL_DIR}/../.. 로 CLI 가 실제로 돈다
        cli = link / ".." / ".." / "scripts" / "sdlc.py"
        self.assertEqual(subprocess.run(["python3", str(cli), "--help"], capture_output=True).returncode, 0)

    def test_copy_install_is_idempotent_and_removable(self):
        self.assertEqual(self.run_bin("--copy").returncode, 0)
        r = self.run_bin("--copy")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_bin("--remove")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.claude_dir / "vibelabs-sdlc").exists())
        self.assertFalse((self.claude_dir / "skills" / "sdlc").exists())

    def test_copy_install_never_overwrites_existing_skill(self):
        mine = self.claude_dir / "skills" / "sdlc"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("작가님 것")
        r = self.run_bin("--copy")
        self.assertEqual(r.returncode, 1)
        self.assertIn("덮어쓰지 않음", r.stderr)
        self.assertEqual((mine / "SKILL.md").read_text(), "작가님 것")
        self.assertFalse((self.claude_dir / "vibelabs-sdlc").exists())

    def test_copy_install_refuses_foreign_home_dir(self):
        (self.claude_dir / "vibelabs-sdlc").mkdir(parents=True)
        r = self.run_bin("--copy")
        self.assertEqual(r.returncode, 1)
        self.assertIn("이 설치기가 만든 것이 아님", r.stderr)

    def test_without_claude_falls_back_to_copy(self):
        r = self.run_bin()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("복사 설치로 진행", r.stdout)
        self.assertTrue((self.claude_dir / "skills" / "sdlc").is_symlink())

    # ------------------------------------------------------------ 플러그인 모드

    def test_plugin_fresh_install(self):
        r = self.run_bin(with_claude=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls_list()
        self.assertIn("plugin marketplace add vibelabs-web/vibelabs-native-sdlc", calls)
        self.assertIn("plugin install vibelabs-sdlc@vibelabs-sdlc --scope user", calls)
        self.assertFalse((self.claude_dir / "vibelabs-sdlc").exists())

    def test_plugin_existing_install_updates(self):
        r = self.run_bin("--scope", "project", with_claude=True,
                         marketplaces=[{"name": "vibelabs-sdlc"}],
                         plugins=[{"id": "vibelabs-sdlc@vibelabs-sdlc", "scope": "project"}])
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls_list()
        self.assertIn("plugin marketplace update vibelabs-sdlc", calls)
        self.assertIn("plugin update vibelabs-sdlc@vibelabs-sdlc --scope project", calls)
        self.assertNotIn("plugin marketplace add vibelabs-web/vibelabs-native-sdlc", calls)

    def test_bad_scope_is_usage_error(self):
        r = self.run_bin("--scope", "global")
        self.assertEqual(r.returncode, 2)

    def test_check_changes_nothing(self):
        r = self.run_bin("--check")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("복사 설치: 미설치", r.stdout)
        self.assertFalse(self.claude_dir.exists())


if __name__ == "__main__":
    unittest.main()
