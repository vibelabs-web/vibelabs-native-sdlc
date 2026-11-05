---
name: sdlc-qc-design
description: SDLC 하네스 3단계(QC Architect 트랙) — 구현 코드를 보기 전, 승인된 spec 만으로 test-spec.md(TC-ID·Given/When/Then·오라클·증거 형식)와 qc-manifest.json·qc-tests/(QC 소유 수용 테스트)를 작성한다. sdlc-plan 과 병렬·독립.
---

# sdlc-qc-design — 독립 Test Spec 트랙

> CLI: `sdlc` = `python3 "${SDLC_HOME:-${CLAUDE_SKILL_DIR}/../..}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

**입력**: 승인된 `spec.md` 만 (plan.md·구현 코드 금지) · **출력**: `test-spec.md`, `qc-manifest.json`, `qc-tests/` · **에이전트**: `sdlc-qc-architect`
**종료 조건**: 모든 must REQ 에 TC, 모든 must TC 에 qc-manifest 명령, skip 표식 0

## 절차 (설계서 §6.3)

1. `sdlc draft <id> test_spec`.
2. **계약 먼저**: REQ 마다 기대 결과·불변조건을 적고, 그다음 TC 를 만든다.
   `TC-ID | REQ-ID | 테스트 레벨 | Given | When | Then(정확한 기대값) | 우선순위 | 증거 형식`
3. 정상·경계(0/최대/최대+1)·음성·권한·동시성·순서를 다룬다. 동시성은 반복 횟수·seed 를 고정한다.
4. 오라클은 spec 의 공개 계약만 사용한다 — **구현 예정 함수명·내부 구조에 묶지 않는다.**
5. spec 이 정하지 않은 동작은 기대값을 만들지 않고 `Gaps / disputes` 에 사양 결함으로 기록 (미결정 REQ 에 TC 를 붙이면 BLOCK).
6. `qc-tests/` 에 실행 가능한 수용 테스트, `qc-manifest.json` 에 TC ↔ 명령:
   ```json
   {"change_id": "CHG-…", "timeout_seconds": 120,
    "cases": [{"tc_id": "TC-001", "cmd": ["python3", "-m", "unittest", "test_x.TC001"], "cwd": ".sdlc/changes/CHG-…/qc-tests"}]}
   ```
   테스트는 환경변수 `SDLC_CHANGE_DIR`(변경 폴더 경로)로 프로젝트 루트를 찾을 수 있다.
7. skip/only/xfail 표식을 넣지 않는다 (QC_TEST_SKIP 오류).

## 위험 등급별 깊이

| 등급 | 다룰 범주 | 필수 REQ당 TC (경고 기준) | 골든 |
|---|---|---|---|
| lite | 정상 | 1개 | 선택 |
| standard | 정상·경계·음성 — 해당 REQ 에 의미 있는 것만 | 3개 | 필수 REQ마다 1개 이상 |
| high | 전 범주 | 상한 없음 | 필수 REQ마다 1개 이상 |

기준을 넘으면 `QC_TC_OVER_BUDGET` 경고가 나온다. 차단은 아니며, REQ 의 위험이 정말 그만큼의 TC 를 요구하는지 다시 본다. 범주를 채우려고 TC 를 늘리지 않는다.

## 골든 데이터셋

test-spec 을 쓰면서 함께 만든다. 입력과 기대값의 쌍을 코드 밖 데이터로 고정해, 승인자가 코드를 읽지 않고도 "이 입력이면 이 결과"를 검토하게 하는 것이 목적이다.

- 위치: `qc-tests/golden/GD-NNN.json` — `qc-tests/` 아래이므로 기준선 승인 때 함께 잠긴다.
  ```json
  {"id": "GD-001", "req_ids": ["REQ-001"], "tc_ids": ["TC-001"], "provenance": "spec-derived",
   "source_ref": "spec.md REQ-001", "input": {"seats_left": 0}, "expected": {"result": "waitlisted"}}
  ```
- `provenance`: `spec-derived`(spec 에서 도출) · `synthetic`(만든 예시) · `approved-sample`(별도 승인받아 비식별 처리한 표본).
- 기대값은 승인된 spec 에서만 가져온다. spec 이 정하지 않은 동작은 골든을 만들지 않고 `Gaps / disputes` 에 기록한다. 미결정 REQ 를 참조하면 오류다.
- **합성 데이터가 원칙이다.** 실제 고객·개인정보를 넣지 않는다. 이메일은 `example.com` 처럼 예약 도메인을 쓴다. 패턴 검사(`GOLDEN_PII_SUSPECT`)는 보조 수단이라 통과해도 실제 데이터가 아니라는 보장이 되지 않는다.
- 테스트는 `qc-tests/golden/` 에서 읽어 판정한다. 파일만 두고 테스트가 읽지 않으면 `GOLDEN_UNUSED` 경고가 나온다.
- `test-spec.md` 의 `Golden dataset` 표에 요약을 적는다.

## 실행 비용 설계 (qc-manifest)

- `setup`: 의존성 설치처럼 한 번만 하면 되는 준비는 TC 명령에 넣지 말고 여기에 둔다. 격리 worktree 에는 gitignore 된 의존성이 없다.
  `"setup": [{"cmd": ["npm", "ci"], "cwd": "."}], "setup_timeout_seconds": 900`
- `max_parallel`: TC 끼리 포트·DB·파일을 공유하지 않을 때만 2 이상으로 둔다. 기본은 1(순차)이다. 판단이 어려우면 올리지 않는다.
- `regression_group`: 함께 깨질 수 있는 TC 를 묶는다. 결함 재검증(`--retest`)이 이 그룹을 같이 돌린다.

## 소유권

- BASELINE_APPROVED 순간 `test-spec.md`·`qc-manifest.json`·`qc-tests/` 가 해시로 잠긴다. 이후 변경은 reopen + QA/PO 재승인.
- 비공개 수용 입력(seed 등)을 쓰더라도 사용자에게 숨겨진 새 요구사항이 되면 안 된다.
