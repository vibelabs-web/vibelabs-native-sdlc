"""승인 검증기 인터페이스 (설계서 §5.3, §7).

- 승인은 state.json 의 approvals[scope] 레코드로만 들어오며, 문서의 status/approval_ref 문자열은 보지 않는다.
- 검증기가 진위를 확인하지 못하면 UNVERIFIABLE → 게이트는 MANUAL_VERIFICATION_REQUIRED (fail-closed).
- local_attested: 로컬 TTY 에서 사람이 확인한 승인. 프로젝트 밖 키로 HMAC 서명. 증거 등급 E1.
- github_review: GitHub PR 리뷰를 API 로 확인 (APPROVED · 작성자≠리뷰어 · 쓰기 권한 · 정책 명단 ·
  리뷰한 커밋의 파일 내용 = 승인 대상 SHA). 증거 등급 E2. 네트워크·gh 불가 시 UNVERIFIABLE.
"""
from __future__ import annotations

import hmac
import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.util import SdlcError, canonical_json, now_iso
from validators.paths import is_within

LEVELS = ["E0", "E1", "E2", "E3"]

VERIFIED, INVALID, UNVERIFIABLE = "VERIFIED", "INVALID", "UNVERIFIABLE"


@dataclass
class VerifyResult:
    status: str
    level: str
    reason: str
    actor: str | None = None


def key_path() -> Path:
    env = os.environ.get("SDLC_APPROVAL_KEY_FILE")
    return Path(env).expanduser() if env else Path.home() / ".config" / "vibelabs-sdlc" / "approval.key"


def load_key(project_root: Path, create: bool = False) -> bytes | None:
    kp = key_path()
    if is_within(project_root, kp):
        raise SdlcError(f"승인 키 {kp} 가 프로젝트 안에 있음 — 커밋·열람 위험으로 거부")
    if not kp.is_file():
        if not create:
            return None
        kp.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(kp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    return kp.read_text().strip().encode()


def _mac(key: bytes, change_id: str, record: dict) -> str:
    payload = {k: v for k, v in record.items() if k != "mac"}
    payload["change_id"] = change_id
    return hmac.new(key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()


def make_local_record(project_root: Path, change_id: str, scope: str, bound: dict, approver: str) -> dict:
    key = load_key(project_root, create=True)
    rec = {"scope": scope, "kind": "local_attested", "ref": f"local:{uuid.uuid4()}",
           "approver": approver, "at": now_iso(), "bound": bound}
    rec["mac"] = _mac(key, change_id, rec)
    return rec


class ApprovalVerifier:
    kind = ""

    def verify(self, project_root: Path, change_id: str, record: dict) -> VerifyResult:  # pragma: no cover
        raise NotImplementedError


class LocalAttestedVerifier(ApprovalVerifier):
    kind = "local_attested"

    def verify(self, project_root, change_id, record):
        key = load_key(project_root)
        if key is None:
            return VerifyResult(INVALID, "E0", f"승인 키 없음 ({key_path()}) — 이 환경에서 서명된 승인이 아님, 재승인 필요")
        mac = record.get("mac")
        if not isinstance(mac, str) or not hmac.compare_digest(mac, _mac(key, change_id, record)):
            return VerifyResult(INVALID, "E0", "로컬 승인 서명 불일치 — 손으로 쓴 승인 레코드로 판단")
        return VerifyResult(VERIFIED, "E1", f"로컬 TTY 승인 ({record.get('approver')}, {record.get('at')})")


class GitHubReviewVerifier(ApprovalVerifier):
    """PR 리뷰 승인 검증 (M2). record: {ref: 리뷰 URL, bound: {artifact: sha, commit?}, paths: {artifact: repo 경로}}."""
    kind = "github_review"
    WRITE_PERMS = {"admin", "maintain", "write"}

    def verify(self, project_root, change_id, record):
        from core import github, policy
        parsed = github.parse_review_url(record.get("ref", ""))
        if not parsed:
            return VerifyResult(INVALID, "E0", f"리뷰 URL 형식 아님: {record.get('ref')!r}")
        owner, repo, pr, review_id = parsed
        expected = github.repo_slug(project_root)
        if expected and f"{owner}/{repo}".lower() != expected.lower():
            return VerifyResult(INVALID, "E0", f"리뷰 레포 {owner}/{repo} ≠ 이 프로젝트 {expected}")
        base = f"repos/{owner}/{repo}"
        gh = github.client()
        try:
            review = gh.api(f"{base}/pulls/{pr}/reviews/{review_id}")
            pull = gh.api(f"{base}/pulls/{pr}")
            reviewer = (review.get("user") or {}).get("login", "")
            if review.get("state") != "APPROVED":
                return VerifyResult(INVALID, "E0", f"리뷰 상태 {review.get('state')} — APPROVED 아님", reviewer)
            author = (pull.get("user") or {}).get("login", "")
            if reviewer.lower() == author.lower():
                return VerifyResult(INVALID, "E0", f"PR 작성자 {author} 의 자기 승인", reviewer)
            allowed = policy.allowed_reviewers(project_root, record.get("scope", ""))
            is_bot = (review.get("user") or {}).get("type") == "Bot" or reviewer.endswith("[bot]")
            if is_bot:
                # 봇(GitHub App) 승인은 정책 명단에 그 봇이 명시된 스코프에서만 인정한다
                if allowed is None or reviewer.lower() not in allowed:
                    return VerifyResult(INVALID, "E0", f"봇 {reviewer} 은 {policy.POLICY_REL} 의 "
                                                       f"{record.get('scope')} 명단에 없음 — 봇 승인 불인정", reviewer)
            else:
                perm = gh.api(f"{base}/collaborators/{reviewer}/permission").get("permission")
                if perm not in self.WRITE_PERMS:
                    return VerifyResult(INVALID, "E0", f"{reviewer} 권한 {perm} — 승인 권한 없음", reviewer)
            if allowed is not None and reviewer.lower() not in allowed:
                return VerifyResult(INVALID, "E0",
                                    f"{reviewer} 는 정책상 {record.get('scope')} 승인자 아님 ({policy.POLICY_REL})", reviewer)
            commit = review.get("commit_id")
            bound = record.get("bound") or {}
            if "commit" in bound and bound["commit"] != commit:
                return VerifyResult(INVALID, "E0", f"리뷰 커밋 {str(commit)[:12]} ≠ 승인 대상 커밋 "
                                                   f"{str(bound['commit'])[:12]}", reviewer)
            for art, sha in bound.items():
                if art in ("commit", "qc_run"):
                    continue
                path = (record.get("paths") or {}).get(art)
                if not path or not path.startswith(f".sdlc/changes/{change_id}/"):
                    return VerifyResult(INVALID, "E0", f"{art} 경로가 변경 폴더 밖이거나 없음: {path!r}", reviewer)
                remote = _remote_sha(gh, base, commit, path, art)
                if remote != sha:
                    return VerifyResult(INVALID, "E0", f"리뷰한 커밋의 {path} 내용 ≠ 승인 대상 — 리뷰 이후 바뀐 내용", reviewer)
        except github.GhUnavailable as e:
            return VerifyResult(UNVERIFIABLE, "E0", f"GitHub 확인 불가: {e}")
        except github.GhError as e:
            if e.status == 404:
                return VerifyResult(INVALID, "E0", f"리뷰/PR 를 찾을 수 없음: {record.get('ref')}")
            return VerifyResult(UNVERIFIABLE, "E0", str(e))
        return VerifyResult(VERIFIED, "E2", f"GitHub PR #{pr} 리뷰 승인 ({reviewer}, {review.get('submitted_at')})",
                            reviewer)


def _remote_sha(gh, base: str, commit: str, path: str, art: str) -> str | None:
    from core import github
    from core.hashing import sha256_bytes
    if art != "qc_tests":
        try:
            return gh.api(f"{base}/contents/{path}?ref={commit}").get("sha")
        except github.GhError as e:
            if e.status == 404:
                return None
            raise
    tree = gh.api(f"{base}/git/trees/{commit}?recursive=1")
    prefix = path.rstrip("/") + "/"
    rows = []
    for t in tree.get("tree", []):
        p = t.get("path", "")
        if t.get("type") == "blob" and p.startswith(prefix) and "__pycache__" not in p.split("/"):
            rows.append((tuple(p[len(prefix):].split("/")), t["sha"]))
    if not rows:
        return None
    return sha256_bytes("\n".join(f"{'/'.join(r)}:{sha}" for r, sha in sorted(rows)).encode())


REGISTRY: dict[str, ApprovalVerifier] = {v.kind: v for v in (LocalAttestedVerifier(), GitHubReviewVerifier())}


def verify(project_root: Path, change_id: str, record: dict | None) -> VerifyResult:
    if not record:
        return VerifyResult(INVALID, "E0", "승인 레코드 없음")
    v = REGISTRY.get(record.get("kind"))
    if v is None:
        return VerifyResult(INVALID, "E0", f"알 수 없는 승인 종류 {record.get('kind')!r}")
    return v.verify(project_root, change_id, record)


def meets(level: str, required: str) -> bool:
    return LEVELS.index(level) >= LEVELS.index(required)
