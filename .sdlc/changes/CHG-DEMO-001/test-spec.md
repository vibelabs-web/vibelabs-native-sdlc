---
change_id: CHG-DEMO-001
revision: 0.1.0
status: draft
author_role: qc-architect
source_refs: [REQ-001, REQ-002, REQ-003]
approval_ref: null
---
# Test Spec: 행사 신청 및 자동 승격 (초안)

**주의:** 이 테스트는 예시이며 승인된 명세·실제 코드 기반 실행 증거가 없다.

| TC-ID | REQ-ID | Given | When | Then | 수준 |
|---|---|---|---|---|---|
| TC-001 | REQ-001 | 29명이 확정됨 | 새 신청 1명 | 확정 30명 | API |
| TC-002 | REQ-002 | 30명이 확정됨 | 31번째 신청 | 확정 30명, 대기 1명(1번) | API |
| TC-003 | REQ-003 | 30명 확정+대기 1명 | 기존 참가자 1명 취소 | 확정 30명, 대기 1번 승격 | API |
| TC-004 | REQ-001 | 확정 29명, 병렬 요청 2개 | 동시에 신청 | 확정 30명 이하 | 동시성 |

## Pending
중복 신청 처리는 요구사항 미정이므로 TC의 기대값을 확정하지 않는다.
