"""GitHub REST 클라이언트 (`gh api` 위임). 인증은 사용자의 gh 로그인을 그대로 쓴다 — 토큰을 저장하지 않는다.

- SDLC_GITHUB_OFFLINE=1 이면 모든 호출이 GhUnavailable (테스트·오프라인에서 결정적 fail-closed).
- 테스트는 set_client() 로 가짜 클라이언트를 주입한다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


class GhError(Exception):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


class GhUnavailable(GhError):
    """gh 미설치·미인증·네트워크 불가 — 검증 불가(UNVERIFIABLE)로 처리."""


class GhClient:
    def api(self, path: str, method: str = "GET", body: dict | None = None):
        if os.environ.get("SDLC_GITHUB_OFFLINE") == "1":
            raise GhUnavailable("SDLC_GITHUB_OFFLINE=1")
        cmd = ["gh", "api", "-X", method, "-H", "Accept: application/vnd.github+json", path]
        if body is not None:
            cmd += ["--input", "-"]
        try:
            p = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                               capture_output=True, text=True, timeout=60)
        except FileNotFoundError as e:
            raise GhUnavailable("gh CLI 없음") from e
        except subprocess.TimeoutExpired as e:
            raise GhUnavailable("GitHub API 시간 초과") from e
        if p.returncode != 0:
            err = (p.stderr or p.stdout).strip()
            m = re.search(r"HTTP (\d{3})", err)
            status = int(m.group(1)) if m else None
            if status is None:
                raise GhUnavailable(f"gh api 실패: {err[:200]}")
            raise GhError(f"GitHub {status}: {err[:200]}", status)
        return json.loads(p.stdout) if p.stdout.strip() else None


_client: GhClient | None = None


def client() -> GhClient:
    global _client
    if _client is None:
        _client = GhClient()
    return _client


def set_client(c: GhClient | None) -> None:
    global _client
    _client = c


_REMOTE_RE = re.compile(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
REVIEW_URL_RE = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)#pullrequestreview-(\d+)$")


def repo_slug(root: Path) -> str | None:
    env = os.environ.get("SDLC_GITHUB_REPO")
    if env:
        return env
    p = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    m = _REMOTE_RE.search(p.stdout.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def parse_review_url(url: str) -> tuple[str, str, int, int] | None:
    m = REVIEW_URL_RE.match(url or "")
    return (m.group(1), m.group(2), int(m.group(3)), int(m.group(4))) if m else None
