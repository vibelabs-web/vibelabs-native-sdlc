import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
SCRIPTS = HARNESS / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import fixtures as fx  # noqa: E402


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.sb = fx.Sandbox()

    def tearDown(self):
        self.sb.close()

    def cli(self, *args, stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "sdlc.py"), "--root", str(self.sb.root), *args],
                              capture_output=True, text=True, input=stdin, env={**os.environ})

    def cli_json(self, *args):
        p = self.cli(*args, "--json")
        return p.returncode, json.loads(p.stdout) if p.stdout.strip() else None

    @staticmethod
    def codes(issues):
        return {i.code for i in issues}
