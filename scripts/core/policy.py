"""조직 정책: `.sdlc/policies/approvers.json` — 스코프별 승인 가능 GitHub 계정과 필수 CI 체크.

이 파일 자체가 승인 권한의 원천이므로 CODEOWNERS 로 보호해야 한다 (docs/branch-protection.md).
"""
from __future__ import annotations

from pathlib import Path

from core.util import SdlcError, read_json

POLICY_REL = ".sdlc/policies/approvers.json"
DEFAULT_REQUIRED_CHECKS = ["validate"]


def load(root: Path) -> dict | None:
    p = root / POLICY_REL
    if not p.is_file():
        return None
    try:
        data = read_json(p)
    except ValueError as e:
        raise SdlcError(f"{POLICY_REL} JSON 오류: {e}") from e
    if not isinstance(data.get("scopes", {}), dict):
        raise SdlcError(f"{POLICY_REL}: scopes 는 객체여야 함")
    return data


def allowed_reviewers(root: Path, scope: str) -> list[str] | None:
    """None = 정책 없음(스코프 제한 없음). [] = 아무도 승인 불가."""
    pol = load(root)
    if pol is None or scope not in pol.get("scopes", {}):
        return None
    return [str(x).lower() for x in pol["scopes"][scope]]


def required_checks(root: Path) -> list[str]:
    pol = load(root)
    return list((pol or {}).get("required_checks", DEFAULT_REQUIRED_CHECKS))


def distinct_security_reviewer(root: Path) -> bool:
    """high-risk 의 security 승인자가 plan_test 승인자와 달라야 하는지 (기본 True, 완전 자율 정책은 False)."""
    return bool((load(root) or {}).get("require_distinct_security_reviewer", True))
