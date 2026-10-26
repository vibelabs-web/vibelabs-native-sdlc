"""업무 등급 분류 (SOP §1). 정보가 부족하면 standard 이상, 보안 키워드는 high-risk 고정."""
from __future__ import annotations

import re

HIGH_RISK_PATTERNS = [
    r"인증", r"로그인", r"비밀번호", r"권한", r"결제", r"환불", r"카드", r"개인정보", r"주민",
    r"마이그레이션", r"규제", r"법규", r"암호", r"토큰", r"시크릿",
    r"\bauth", r"login", r"password", r"oauth", r"payment", r"billing", r"\bpii\b",
    r"personal data", r"gdpr", r"migration", r"secret", r"credential", r"encrypt",
]
LITE_PATTERNS = [r"오타", r"문구", r"맞춤법", r"typo", r"wording", r"\bdocs?\b", r"readme"]

LEVELS = ["lite", "standard", "high"]


def classify(text: str) -> tuple[str, list[str]]:
    low = text.lower()
    hits = [p for p in HIGH_RISK_PATTERNS if re.search(p, low)]
    if hits:
        return "high", hits
    if any(re.search(p, low) for p in LITE_PATTERNS):
        return "lite", []
    return "standard", []


def resolve(requested: str | None, text: str) -> tuple[str, list[str], str | None]:
    """요청 등급과 자동 분류 중 더 높은 쪽을 쓴다. 반환: (level, hits, warning)."""
    auto, hits = classify(text)
    if requested in (None, "auto"):
        return auto, hits, None
    if requested not in LEVELS:
        raise ValueError(f"unknown risk level: {requested}")
    if LEVELS.index(requested) < LEVELS.index(auto):
        return auto, hits, f"요청 등급 {requested} 무시 — 키워드 {hits} 로 {auto} 고정 (하향 불가)"
    return requested, hits, None
