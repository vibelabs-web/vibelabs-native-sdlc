"""파일 해시. 기준선은 git blob SHA(40자)로 기록한다 — git 없이도 동일 값을 계산할 수 있다."""
from __future__ import annotations

import hashlib
from pathlib import Path


def git_blob_sha_bytes(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def git_blob_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return git_blob_sha_bytes(path.read_bytes())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())
