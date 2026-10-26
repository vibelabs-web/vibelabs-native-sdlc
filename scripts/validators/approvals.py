"""승인 검증기 인터페이스 (설계서 §5.3, §7).

- 승인은 state.json 의 approvals[scope] 레코드로만 들어오며, 문서의 status/approval_ref 문자열은 보지 않는다.
- 검증기가 진위를 확인하지 못하면 UNVERIFIABLE → 게이트는 MANUAL_VERIFICATION_REQUIRED (fail-closed).
- local_attested: 로컬 TTY 에서 사람이 확인한 승인. 프로젝트 밖 키로 HMAC 서명. 증거 등급 E1.
- github_review: 인터페이스만. 오프라인 MVP 에서는 항상 UNVERIFIABLE.
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
    """M2 연동 지점. PR 리뷰 ID·승인자 권한·커밋 일치를 GitHub API 로 확인해야 한다 — 미구현."""
    kind = "github_review"

    def verify(self, project_root, change_id, record):
        return VerifyResult(UNVERIFIABLE, "E0",
                            f"외부 승인 원본 {record.get('ref')} 를 검증할 신뢰 서비스가 연결되지 않음 (미구현)")


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
