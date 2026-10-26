"""승인 전담 기계 신원: GitHub App (봇).

계정이 하나뿐이면 GitHub 는 PR 작성자의 자기 승인을 막는다. 그래서 승인 리뷰는 사용자 계정이 아니라
이 App 의 설치 토큰으로 남긴다. 리뷰를 남길지는 LLM 이 아니라 `sdlc auto-approve` 의 결정적 규칙이 정한다.

- 설정: ~/.config/vibelabs-sdlc/app.json (+ 0600 개인키). 프로젝트 안에는 두지 않는다.
- JWT(RS256) 서명은 `openssl` 로 한다 (표준 라이브러리에 RSA 가 없음).
- `setup()` 은 GitHub App Manifest 흐름: 로컬 콜백 서버 → 브라우저에서 작가님이 "Create" 클릭 → 코드 교환.
"""
from __future__ import annotations

import base64
import http.server
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from core import github
from core.util import SdlcError, atomic_write_json, read_json

API = "https://api.github.com"


def config_dir() -> Path:
    env = os.environ.get("SDLC_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".config" / "vibelabs-sdlc"


def config_path() -> Path:
    return config_dir() / "app.json"


def load_config() -> dict | None:
    p = config_path()
    return read_json(p) if p.is_file() else None


def bot_login(cfg: dict | None = None) -> str | None:
    cfg = cfg or load_config()
    return f"{cfg['slug']}[bot]" if cfg else None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(app_id: int | str, pem_path: Path, now: int | None = None) -> str:
    now = int(now or time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)},
                                 separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    p = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(pem_path)], input=signing_input,
                       capture_output=True)
    if p.returncode != 0:
        raise SdlcError(f"JWT 서명 실패: {p.stderr.decode(errors='replace')[:200]}")
    return f"{header}.{payload}.{_b64url(p.stdout)}"


def _http(method: str, url: str, token: str | None = None, body: dict | None = None, bearer: bool = True):
    if os.environ.get("SDLC_GITHUB_OFFLINE") == "1":
        raise github.GhUnavailable("SDLC_GITHUB_OFFLINE=1")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"{'Bearer' if bearer else 'token'} {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise github.GhError(f"GitHub {e.code}: {e.read()[:200]!r}", e.code) from e
    except urllib.error.URLError as e:
        raise github.GhUnavailable(f"GitHub 연결 실패: {e.reason}") from e


_token_cache: dict[str, tuple[str, float]] = {}


def installation_token(repo: str, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    if not cfg:
        raise SdlcError("GitHub App 미설정 — `sdlc github-app setup` 먼저")
    hit = _token_cache.get(repo)
    if hit and hit[1] > time.time() + 120:
        return hit[0]
    jwt = make_jwt(cfg["app_id"], Path(cfg["pem_path"]))
    try:
        inst = _http("GET", f"{API}/repos/{repo}/installation", jwt)
    except github.GhError as e:
        if e.status == 404:
            raise SdlcError(f"App {cfg['slug']} 이 {repo} 에 설치되지 않음 — "
                            f"https://github.com/apps/{cfg['slug']}/installations/new") from e
        raise
    tok = _http("POST", f"{API}/app/installations/{inst['id']}/access_tokens", jwt, {})
    _token_cache[repo] = (tok["token"], time.time() + 3300)
    return tok["token"]


_app_client: github.GhClient | None = None


def app_client(repo: str) -> github.GhClient:
    """봇 신원 클라이언트. 테스트는 set_app_client() 로 주입."""
    if _app_client is not None:
        return _app_client
    return github.GhClient(token=installation_token(repo))


def set_app_client(c: github.GhClient | None) -> None:
    global _app_client
    _app_client = c


# ------------------------------------------------------------------ setup (manifest flow)

def manifest(repo: str, callback: str, name: str) -> dict:
    return {
        "name": name,
        "url": f"https://github.com/{repo}",
        "hook_attributes": {"url": "https://example.invalid/sdlc-hook", "active": False},
        "redirect_url": callback,
        "public": False,
        "default_permissions": {"pull_requests": "write", "contents": "read", "checks": "read",
                                "metadata": "read"},
        "default_events": [],
        "description": "VibeLabs SDLC harness gatekeeper — approves PRs only when `sdlc auto-approve` gate rules pass.",
    }


def setup(repo: str, name: str | None = None, open_browser: bool = True, timeout: int = 600) -> dict:
    if load_config():
        raise SdlcError(f"이미 설정됨: {config_path()} — 다시 만들려면 그 파일을 먼저 치우세요")
    owner = repo.split("/")[0]
    state = secrets.token_hex(8)
    name = name or f"vibelabs-sdlc-gatekeeper-{secrets.token_hex(2)}"
    result: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/":
                cb = f"http://127.0.0.1:{self.server.server_port}/callback"
                m = json.dumps(manifest(repo, cb, name)).replace("'", "&#39;")
                html = (f"<html><body><p>GitHub App 생성 페이지로 이동합니다…</p>"
                        f"<form id=f method=post action='https://github.com/settings/apps/new?state={state}'>"
                        f"<input type=hidden name=manifest value='{m}'></form>"
                        f"<script>document.getElementById('f').submit()</script></body></html>")
                self._send(200, html)
            elif u.path == "/callback" and q.get("state", [""])[0] == state and "code" in q:
                result["code"] = q["code"][0]
                self._send(200, "<html><body><h3>완료 — 터미널로 돌아가세요.</h3></body></html>")
            else:
                self._send(400, "bad request")

        def _send(self, code, html):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    start_url = f"http://127.0.0.1:{srv.server_port}/"
    print(f"브라우저에서 GitHub App 을 만듭니다 ({owner} 계정): {start_url}\n"
          f"GitHub 화면에서 'Create GitHub App' 을 누르세요.", flush=True)
    if open_browser:
        webbrowser.open(start_url)
    deadline = time.time() + timeout
    while "code" not in result and time.time() < deadline:
        time.sleep(0.5)
    srv.shutdown()
    if "code" not in result:
        raise SdlcError("시간 초과 — App 생성이 완료되지 않음")
    conv = _http("POST", f"{API}/app-manifests/{result['code']}/conversions", body={})
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    pem = d / f"app-{conv['slug']}.pem"
    fd = os.open(str(pem), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(conv["pem"])
    cfg = {"app_id": conv["id"], "slug": conv["slug"], "pem_path": str(pem), "html_url": conv["html_url"],
           "owner": (conv.get("owner") or {}).get("login", owner)}
    atomic_write_json(config_path(), cfg)
    os.chmod(config_path(), 0o600)
    return cfg
