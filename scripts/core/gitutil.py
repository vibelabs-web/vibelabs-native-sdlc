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


def upstream_ref(root: Path) -> str | None:
    """원격 기본 브랜치 (origin/HEAD → 예: origin/main). 없으면 None."""
    r = _git(root, "rev-parse", "--abbrev-ref", "origin/HEAD")
    ref = r.stdout.strip()
    return ref if r.returncode == 0 and ref and ref != "origin/HEAD" else None


def branch_changed_files(root: Path, base: str, upstream: str | None) -> list[str] | None:
    """base 이후 이 브랜치가 직접 만든 커밋(머지 커밋·upstream 에 이미 있는 커밋 제외)이 바꾼 파일."""
    args = ["log", "--no-merges", "--format=", "--name-only", f"{base}..HEAD"]
    if upstream:
        args += ["--not", upstream]
    r = _git(root, *args)
    if r.returncode != 0:
        return None
    return sorted({p for p in r.stdout.splitlines() if p.strip()})


def same_code(root: Path, a: str | None, b: str | None) -> bool:
    """a 와 b 가 같은 제품 코드인가: 같은 커밋이거나, a 가 b 의 조상이고 그 사이 변경이 `.sdlc/` 뿐.

    자율 모드에서는 상태·증거를 PR 에 올리려고 커밋하므로, 그 커밋 때문에 증거가 무효가 되면 끝나지 않는다.
    `.sdlc/` 안의 기준 문서·QC 자산은 기준선·잠금 해시가 따로 지킨다.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    if _git(root, "merge-base", "--is-ancestor", a, b).returncode != 0:
        return False
    files = changed_files(root, a, b)
    return files is not None and all(f.startswith(".sdlc/") for f in files)
