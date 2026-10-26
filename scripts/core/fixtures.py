"""하네스 자체 테스트·평가용 임시 프로젝트 빌더 (tests/ 와 `sdlc eval` 이 공유).

승인은 TTY 를 거치지 않고 라이브러리로 직접 서명한다 — 테스트 전용 키(SDLC_APPROVAL_KEY_FILE)를 쓸 때만 허용.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from core import demo, lifecycle
from core.changes import HARNESS_ROOT, Project
from validators import approvals, gate as g

FIXTURES = HARNESS_ROOT / "evals" / "fixtures"
PATH_TO = [
    "INTENT_APPROVED", "SPEC_DRAFT", "SPEC_APPROVED", "PLAN_TEST_DRAFT", "BASELINE_APPROVED",
    "BUILDING", "QC_RUNNING",
]
SCOPE_AT = {"INTENT_APPROVED": "intent", "SPEC_APPROVED": "spec", "BASELINE_APPROVED": "plan_test"}


class Sandbox:
    """임시 git 리포 + 프로젝트 밖 테스트 승인 키."""

    def __init__(self):
        self.base = Path(tempfile.mkdtemp(prefix="sdlc-sandbox-"))
        self.root = self.base / "repo"
        self.root.mkdir()
        self.key = self.base / "approval.key"
        self._old_env = {k: os.environ.get(k) for k in ("SDLC_APPROVAL_KEY_FILE", "SDLC_GITHUB_OFFLINE", "SDLC_GITHUB_REPO")}
        os.environ["SDLC_APPROVAL_KEY_FILE"] = str(self.key)
        os.environ["SDLC_GITHUB_OFFLINE"] = "1"  # 샌드박스는 외부 호출 없음 — 필요한 테스트만 가짜 클라이언트 주입
        os.environ.pop("SDLC_GITHUB_REPO", None)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "sandbox")
        git(self.root, "config", "user.email", "sandbox@example.invalid")
        git(self.root, "config", "commit.gpgsign", "false")
        self.project = Project(self.root)

    def close(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from core import github
        github.set_client(None)
        subprocess.run(["git", "-C", str(self.root), "worktree", "prune"], capture_output=True)
        shutil.rmtree(self.base, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def commit(self, msg: str = "change") -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "--allow-empty", "-m", msg)
        return git(self.root, "rev-parse", "HEAD").strip()

    def demo(self, impl: str | None = None, change_id: str = "CHG-DEMO-001"):
        ch = demo.init(self.project, change_id=change_id)
        if impl:
            self.use_impl(impl)
        self.commit("demo init")
        return self.project.load(ch.id)

    def use_impl(self, name: str) -> None:
        src = FIXTURES / f"{name}.py" if name != "correct" else HARNESS_ROOT / "examples/event-registration/app/registration.py"
        shutil.copy(src, self.root / "app" / "registration.py")

    def reload(self, ch):
        return self.project.load(ch.id)


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout


def approve(ch, scope: str) -> None:
    bound = g.current_bound(ch, scope)
    ch.state.setdefault("approvals", {})[scope] = approvals.make_local_record(
        ch.project.root, ch.id, scope, bound, "sandbox-approver")
    ch.save()


def self_check_cmd() -> list[str]:
    return [sys.executable, "-m", "unittest", "discover", "-s", "app", "-p", "test_*.py"]


def advance(sb: Sandbox, ch, until: str = "QC_RUNNING"):
    """승인·자체 검사를 채워 넣으며 until 단계까지 전이한다. 막히면 GateResult 를 돌려준다."""
    for target in PATH_TO:
        ch = sb.reload(ch)
        if target in SCOPE_AT:
            approve(ch, SCOPE_AT[target])
        if target == "QC_RUNNING":
            lifecycle.build_check(ch, self_check_cmd())
            ch = sb.reload(ch)
        res = g.gate(ch, target)
        if res.decision != g.ALLOW:
            return ch, res
        g.apply(ch, res)
        if target == until:
            break
    return sb.reload(ch), None


def to_building_again(sb: Sandbox, ch):
    """DEFECT_OPEN → BUILDING."""
    res = g.gate(ch, "BUILDING")
    if res.decision == g.ALLOW:
        g.apply(ch, res)
    return sb.reload(ch), res


def to_qc_running(sb: Sandbox, ch):
    lifecycle.build_check(ch, self_check_cmd())
    ch = sb.reload(ch)
    res = g.gate(ch, "QC_RUNNING")
    if res.decision == g.ALLOW:
        g.apply(ch, res)
    return sb.reload(ch), res
