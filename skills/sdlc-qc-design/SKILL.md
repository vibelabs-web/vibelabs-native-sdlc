---
name: sdlc-qc-design
description: SDLC 하네스 3단계(QC Architect 트랙) — 구현 코드를 보기 전, 승인된 spec 만으로 test-spec.md(TC-ID·Given/When/Then·오라클·증거 형식)와 qc-manifest.json·qc-tests/(QC 소유 수용 테스트)를 작성한다. sdlc-plan 과 병렬·독립.
---

# sdlc-qc-design — 독립 Test Spec 트랙

> CLI: `sdlc` = `python3 "${SDLC_HOME:-$HOME/.claude/skills/sdlc}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

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

## 소유권

- BASELINE_APPROVED 순간 `test-spec.md`·`qc-manifest.json`·`qc-tests/` 가 해시로 잠긴다. 이후 변경은 reopen + QA/PO 재승인.
- 비공개 수용 입력(seed 등)을 쓰더라도 사용자에게 숨겨진 새 요구사항이 되면 안 된다.
