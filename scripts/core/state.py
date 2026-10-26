"""상태 기계 (SOP §3) 와 기준선 무효화 표 (SOP §6)."""
from __future__ import annotations

STAGES = [
    "INTAKE", "INTENT_DRAFT", "INTENT_APPROVED", "SPEC_DRAFT", "SPEC_APPROVED",
    "PLAN_TEST_DRAFT", "BASELINE_APPROVED", "BUILDING", "QC_RUNNING", "DEFECT_OPEN",
    "QC_PASSED", "REVIEW_PENDING", "RELEASE_APPROVED", "MONITORING",
]

TRANSITIONS: dict[str, list[str]] = {
    "INTAKE": ["INTENT_DRAFT"],
    "INTENT_DRAFT": ["INTENT_APPROVED"],
    "INTENT_APPROVED": ["SPEC_DRAFT"],
    "SPEC_DRAFT": ["SPEC_APPROVED"],
    "SPEC_APPROVED": ["PLAN_TEST_DRAFT"],
    "PLAN_TEST_DRAFT": ["BASELINE_APPROVED"],
    "BASELINE_APPROVED": ["BUILDING"],
    "BUILDING": ["QC_RUNNING"],
    "QC_RUNNING": ["DEFECT_OPEN", "BASELINE_APPROVED", "QC_PASSED"],
    "DEFECT_OPEN": ["BUILDING"],
    "QC_PASSED": ["REVIEW_PENDING"],
    "REVIEW_PENDING": ["RELEASE_APPROVED", "BUILDING"],
    "RELEASE_APPROVED": ["MONITORING"],
    "MONITORING": ["INTENT_DRAFT"],
}

# 되돌림(reopen) 허용 목적지: 기준선을 다시 잡아야 하는 초안 단계
REOPEN_TARGETS = ["INTENT_DRAFT", "SPEC_DRAFT", "PLAN_TEST_DRAFT"]

# 산출물 → 승인 스코프. 승인은 이 산출물들의 SHA 에 묶인다.
APPROVAL_SCOPES: dict[str, list[str]] = {
    "intent": ["intent"],
    "spec": ["intent", "spec"],
    "plan_test": ["spec", "plan", "test_spec", "qc_manifest", "qc_tests"],
    "release": [],
    "security": ["spec", "plan", "test_spec"],  # high-risk 추가 승인 (보안/정책 소유자)
}

# 산출물 변경 시 무효화(stale)되는 대상 (SOP §6)
INVALIDATION: dict[str, list[str]] = {
    "intent": ["spec", "plan", "test_spec", "evidence"],
    "spec": ["plan", "test_spec", "evidence"],
    "plan": ["evidence"],
    "test_spec": ["evidence"],
    "qc_manifest": ["evidence"],
    "qc_tests": ["evidence"],
}

# reopen 목적지에서 지워야 하는 승인
REOPEN_CLEARS: dict[str, list[str]] = {
    "INTENT_DRAFT": ["intent", "spec", "plan_test", "security", "release"],
    "SPEC_DRAFT": ["spec", "plan_test", "security", "release"],
    "PLAN_TEST_DRAFT": ["plan_test", "security", "release"],
}

BUG_TRANSITIONS: dict[str, list[str]] = {
    "open": ["triaged", "blocked_spec", "escalated"],
    "triaged": ["in_progress", "blocked_spec", "escalated"],
    "in_progress": ["ready_for_retest", "blocked_spec", "escalated"],
    "ready_for_retest": ["verified_fixed", "reopened"],  # QC 재실행만
    "reopened": ["in_progress", "escalated"],
    "verified_fixed": ["closed"],
    "blocked_spec": ["triaged"],
    "escalated": ["triaged"],  # 사람 결정 필요 (TTY)
    "closed": [],
}
QC_ONLY_BUG_TARGETS = {"verified_fixed", "reopened"}
HUMAN_ONLY_BUG_FROM = {"escalated", "blocked_spec"}
RESOLVED_BUG_STATES = {"verified_fixed", "closed"}


def allowed_next(stage: str) -> list[str]:
    return TRANSITIONS.get(stage, [])
