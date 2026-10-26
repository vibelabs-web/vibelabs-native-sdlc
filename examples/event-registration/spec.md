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
