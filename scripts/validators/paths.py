"""경로 검증: 상대경로 정규화, 절대경로·`..`·symlink escape 차단."""
from __future__ import annotations

import os
from pathlib import Path


class PathEscape(ValueError):
    pass


def safe_join(root: Path, rel: str) -> Path:
    """root 아래의 실제 경로를 돌려준다. 밖을 가리키면 PathEscape."""
    if not rel or "\0" in rel:
        raise PathEscape(f"빈 경로 또는 NUL 포함: {rel!r}")
    if os.path.isabs(rel) or rel.startswith("~"):
        raise PathEscape(f"절대경로 금지: {rel}")
    root_real = Path(os.path.realpath(root))
    target = Path(os.path.realpath(root_real / rel))
    if target != root_real and root_real not in target.parents:
        raise PathEscape(f"루트 밖 경로: {rel} → {target}")
    return target


def normalize_rel(root: Path, rel: str) -> str:
    return safe_join(root, rel).relative_to(Path(os.path.realpath(root))).as_posix()


def is_within(root: Path, candidate: Path) -> bool:
    root_real = Path(os.path.realpath(root))
    cand = Path(os.path.realpath(candidate))
    return cand == root_real or root_real in cand.parents
