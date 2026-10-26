---
name: sdlc-build
description: SDLC 하네스 4단계 — 고정된 spec/plan/test-spec 기준으로 TASK 순서대로 구현하고 자체 검사(sdlc build check)를 기록한 뒤 QC_RUNNING 게이트로 넘긴다. BUG 수정 루프도 이 스킬이 맡는다. stage BASELINE_APPROVED·BUILDING·DEFECT_OPEN.
---

# sdlc-build — Build → 코드·자체 테스트

> CLI: `sdlc` = `python3 "${SDLC_HOME:-$HOME/.claude/skills/sdlc}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

**입력**: 잠긴 spec/plan/test-spec(읽기 전용), 열린 BUG · **출력**: 코드 커밋, 자체 테스트, `build/BUILD-NNN.log` · **에이전트**: `sdlc-builder`
**종료 조건**: `sdlc gate <id> QC_RUNNING` = ALLOW (커밋된 HEAD · 자체 검사 exit 0 · 계획 밖 변경 0)

## 절차

1. stage 가 BASELINE_APPROVED 또는 DEFECT_OPEN 이면 `sdlc gate <id> BUILDING` (빌드 시작 SHA 가 기록됨).
   - DEFECT_OPEN 에서 MANUAL 이면 escalated 결함이 있다 — **멈추고 사람에게 보고.**
2. plan.md 의 TASK 순서대로 구현. 변경 파일은 plan 에 선언된 경로만. 계획 밖 변경이 필요하면 **중지 → 영향 분석 → plan 개정 요청**.
3. lint/unit/build → 커밋 → `sdlc build check <id> -- <자체 검사 명령>` (exit 0, dirty=false).
4. `sdlc drift <id>` 로 계획 밖 변경 확인 → `sdlc gate <id> QC_RUNNING`.

## BUG 수정 루프 (SOP §4 단계 5)

1. `sdlc bug list <id>` → BUG 파일의 재현 절차·기대/실제·SHA·로그를 읽는다.
2. 재현 → 원인 지점 특정 → 수정 → 자체 테스트로 재발하지 않는지 확인 (디버깅 순서).
3. `sdlc bug transition <id> BUG-NNN --to triaged|in_progress --role builder`, 커밋 후 `--to ready_for_retest --role builder`.
4. `verified_fixed`/`reopened` 는 QC 재실행만 판정한다 — Builder 가 바꿀 수 없다.

## 금지 (가드 훅·CI 가 감시)

- `test-spec.md`·`qc-manifest.json`·`qc-tests/` 수정·삭제·skip 삽입 금지 (ORACLE_TAMPERED / QC_TEST_SKIP).
- 실패 테스트 제거·약화로 통과시키기 금지. 테스트 자체가 틀렸다고 보이면 근거를 적어 사람에게.
- secrets 접근·외부 전송·배포 금지.
