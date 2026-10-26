# Requirements Traceability Matrix

**change_id:** CHG-YYYYMMDD-NNN  
**spec SHA:** TBD  
**plan SHA:** TBD  
**test-spec SHA:** TBD

| Intent ID | REQ-ID | TASK-ID | TC-ID | RUN-ID | BUG-ID | 상태 |
|---|---|---|---|---|---|---|
| INT-001 | REQ-001 | TASK-001 | TC-001 | - | - | not-run |

## 자동 검사 규칙
1. 모든 must REQ에 출처 Intent·TASK·TC가 있다.
2. 알려지지 않은 REQ를 참조하는 TASK/TC가 없다.
3. evidence의 실제 코드 SHA와 문서 baseline이 일치한다.
4. 의도/Spec/Test Spec 개정은 해당 하위 증거를 stale 처리한다.
