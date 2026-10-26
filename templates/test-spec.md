---
change_id: CHG-YYYYMMDD-NNN
revision: 0.1.0
status: draft
author_role: qc-architect
source_refs: [REQ-001]
approval_ref: null
---
# Test Spec: <기능 이름>

## Approved contract
- Spec revision / SHA:
- 계약 승인자:
- QC 작성자 (Builder와 별개):

## Test cases (observable acceptance)
| TC-ID | REQ-ID | 테스트 레벨 | 사전 조건(Given) | 행동(When) | 기대 결과(Then) | 우선순위 | 증거 형식 |
|---|---|---|---|---|---|---|---|
| TC-001 | REQ-001 | API | <초기상태> | <입력/행동> | <정확한 기대값> | must | json+log |

## Boundaries & negative paths
- 최솟값/최댓값 / 0 / null:
- 권한 없음/실패 주입:
- 동시성/중복/순서:

## Independent verification
- 공개 테스트:
- QC-only 시드 또는 미공개 수용 입력(새 요구사항이면 안 됨):
- 수행 환경/정확한 명령:
- 테스트 오라클의 출처:

## Gaps / disputes
| ID | 누락된 REQ/모순된 기대값 | 해결 책임자 | 상태 |
|---|---|---|---|

## Test ownership and baseline
- Builder는 승인된 기대값·QC 검증 스위트를 수정하지 않는다.
- 기대값 변경은 Issue + QA/PO 승인 + baseline 갱신 + 회귀 재실행 필요.
- 승인 원본/SHA:
