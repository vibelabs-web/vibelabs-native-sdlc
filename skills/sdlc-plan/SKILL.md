---
name: sdlc-plan
description: SDLC 하네스 3단계(Planner 트랙) — 승인된 spec 으로 TASK-ID 별 구현 계획 plan.md(REQ 연결·변경 파일 경로·순서·위험·대안·롤백·완료 증거)를 작성한다. sdlc-qc-design 과 병렬·독립으로 실행된다.
---

# sdlc-plan — Plan 트랙

> CLI: `sdlc` = `python3 "${SDLC_HOME:-$HOME/.claude/skills/sdlc}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

**입력**: 승인된 `spec.md` 만 (test-spec 초안을 보지 않는다) · **출력**: `plan.md` · **에이전트**: `sdlc-planner`
**종료 조건**: `sdlc validate <id>` 에 plan.md 관련 error 0, 모든 must REQ 에 TASK 연결

## 절차

1. stage 가 SPEC_APPROVED 이면 `sdlc gate <id> PLAN_TEST_DRAFT` → `sdlc draft <id> plan`.
2. 기존 코드 영향을 조사한다 (모듈·API·DB·마이그레이션).
3. `Ordered tasks` 표: `TASK-ID | REQ-ID | 변경 파일/컴포넌트 | 선행조건 | 작업 내용 | 완료 증거`.
   - **변경 파일 열에는 실제 경로**(`app/registration.py`, `src/api/`)를 쓴다 — `sdlc drift` 가 이 열로 계획 밖 변경을 잡는다. 경로가 없으면 드리프트는 '미검증'.
   - 완료 증거 열의 TC-ID 는 QC 트랙이 만든 ID 와 Cross Review 때 맞춘다.
4. 위험·대안·롤백·데이터 호환을 적는다. 범위 밖 작업은 넣지 않는다.

## Cross Review (두 트랙이 끝난 뒤, /sdlc 가 수행)

- `sdlc validate <id> --strict` 로 MISSING_TASK / MISSING_TC / UNKNOWN_REF 0 확인.
- 불일치는 **spec 을 기준으로** 고친다. QC 오라클을 plan 에 맞춰 바꾸지 않는다.
- 끝나면 작가님께 `sdlc approve <id> plan_test` (TTY) 요청 → `sdlc gate <id> BASELINE_APPROVED`.
