"""git 조회. 실패하면 None 을 돌려주고, 호출자가 fail-closed 로 처리한다."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def is_repo(root: Path) -> bool:
    try:
        return _git(root, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    except FileNotFoundError:
        return False


def head(root: Path) -> str | None:
    if not is_repo(root):
        return None
    r = _git(root, "rev-parse", "--verify", "HEAD")
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and len(sha) == 40 else None


def dirty_paths(root: Path) -> list[str] | None:
    """`.sdlc/` 밖의 미커밋 변경 경로. git 이 아니면 None."""
    if not is_repo(root):
        return None
    r = _git(root, "status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude).sdlc")
    if r.returncode != 0:
        return None
    return [line[3:] for line in r.stdout.splitlines() if line.strip()]


def changed_files(root: Path, base: str, target: str = "HEAD") -> list[str] | None:
    r = _git(root, "diff", "--name-only", f"{base}..{target}")
    if r.returncode != 0:
        return None
    return [p for p in r.stdout.splitlines() if p.strip()]


def user_name(root: Path) -> str | None:
    r = _git(root, "config", "user.name")
    return r.stdout.strip() or None


def worktree_add(root: Path, dest: Path, sha: str) -> bool:
    return _git(root, "worktree", "add", "--detach", str(dest), sha).returncode == 0


def worktree_remove(root: Path, dest: Path) -> None:
    _git(root, "worktree", "remove", "--force", str(dest))
