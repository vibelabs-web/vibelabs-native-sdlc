---
change_id: CHG-DEMO-001
revision: 0.1.0
status: draft
author_role: planner
source_refs: [REQ-001, REQ-002, REQ-003]
approval_ref: null
---
# Plan: 행사 신청 및 대기 로직 (데모 — 변경 파일 경로 포함판)

`plan.md` 예시와 같은 TASK 구성에 실제 변경 파일 경로를 넣은 데모용 계획이다. 경로가 있어야 `sdlc drift` 가 계획 밖 변경을 잡을 수 있다.

| TASK-ID | REQ-ID | 변경 파일/컴포넌트 | 선행조건 | 작업 내용 | 완료 증거 |
|---|---|---|---|---|---|
| TASK-001 | REQ-001 | app/registration.py | - | 정원 상한·동시 신청 직렬화 | TC-001, TC-004 |
| TASK-002 | REQ-002 | app/registration.py | TASK-001 | 대기 순번 보존 | TC-002 |
| TASK-003 | REQ-003 | app/registration.py, app/test_registration.py | TASK-002 | 취소 시 첫 대기자 승격 | TC-003 |

## Risks
- 동시 요청으로 정원 초과 위험: 잠금으로 확인·추가를 하나의 임계 구역에 둔다.
- 중복 등록 처리 정책 미결정(OPEN-001) → 해당 동작은 구현·검증하지 않는다.
