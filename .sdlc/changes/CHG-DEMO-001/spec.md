---
change_id: CHG-DEMO-001
revision: 0.1.0
status: draft
author_role: spec-writer
source_refs: [CHG-DEMO-001]
approval_ref: null
---
# Spec: 행사 등록·대기자 전환 (데모 초안)

**미승인 데모 자료**. 실제 개발 전 관련 사용자/PO의 확정 필요.

| REQ-ID | 요구사항 | 출처 | 상태 | 검증 가능한 결과 |
|---|---|---|---|---|
| REQ-001 | 확정 참가자는 언제나 정원 30명을 넘지 않아야 한다. | 데모 Intent | proposed | 동시 등록 포함 확정자 수 ≤ 30 |
| REQ-002 | 31번째 이후 신청은 대기 신청으로 저장하며 순번을 보존한다. | 데모 Intent | proposed | 확정 30명, 초과분 대기 |
| REQ-003 | 확정 참가자가 취소하면 가장 먼저 대기한 신청자를 승격한다. | 데모 Intent | proposed | 정상 취소 시 최선순위 승격 |

## Open questions
- 중복 신청 처리는 미결정. 관련 TC 기대값 확정 금지.
- 신청 취소와 신규 등록이 동시에 발생하는 정책은 상세화 필요.
- 알림 여부와 개인정보 보호 규약 별도 확인 필요.

## Interfaces and data contracts
- 공개 계약(데모 확정 범위): `Event(capacity=30)` — `register(name) -> "confirmed" | "waitlisted"`,
  `cancel(name)`, `confirmed() -> list[str]`(확정 순), `waitlist() -> list[str]`(대기 순).
- QC 수용 테스트는 이 공개 계약만 사용한다. 내부 자료구조·함수에 기대값을 묶지 않는다.
- 중복 신청 시 반환값: **미결정** (OPEN) — 합격 기준 없음.
