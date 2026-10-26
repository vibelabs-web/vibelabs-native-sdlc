---
name: sdlc-spec
description: SDLC 하네스 2단계 — 승인된 intent 에서 REQ-ID 별 단일 검증 가능 요구사항으로 spec.md 를 작성한다(정상·경계·음성·동시성·권한·NFR, 미정의 동작은 OPEN). /sdlc 가 stage INTENT_APPROVED·SPEC_DRAFT 에서 호출한다.
---

# sdlc-spec — Specify → spec.md

> CLI: `sdlc` = `python3 "${SDLC_HOME:-$HOME/.claude/skills/sdlc}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

**입력**: 승인된 `intent.md`(기준선 SHA 고정), 정책, 기존 아키텍처 · **출력**: `spec.md` · **에이전트**: `sdlc-spec-writer`
**종료 조건**: `sdlc gate <id> SPEC_APPROVED --dry-run` BLOCK 사유 0

## 절차 (SOP §4 단계 2, 설계서 §6.2)

1. stage 가 INTENT_APPROVED 이면 `sdlc gate <id> SPEC_DRAFT` → `sdlc draft <id> spec` (이미 있으면 덮어쓰지 않음).
2. 사용자 흐름·상태 전이를 먼저 그린 뒤 REQ-ID 마다 **하나의 관측 가능한 규칙** (WHEN 조건 THEN 결과).
3. `Functional requirements` 표 열: `REQ-ID | 조건·요구행동 | 원천 | 우선순위(must/should/could) | 검증 가능 결과`. 원천(INT/대화/정책)이 없으면 BLOCK.
4. 각 핵심 REQ 에 질문: 기능 누락? 허용되지 않은 경로? 경계값? 부정 케이스? 동시성? 예외? 모호한 정책? — 충분하지 않으면 `OPEN-NNN`.
5. 미결정 요구는 표에 남기되 상태를 `open`/`미결정` 으로 — 필수 커버리지에서 빠지고, **TC 기대값을 붙이면 게이트가 막는다**(ORACLE_FOR_OPEN_REQ).
6. `Interfaces and data contracts` 에 QC 가 블랙박스로 쓸 공개 계약을 적는다 (구현 내부 이름이 아니라 외부에서 관측 가능한 것).
7. ID 는 삭제 후 재사용하지 않는다 (ID_REUSED).

## 금지

- intent 에 없는 목표를 추가하지 않는다 — 필요하면 사용자에게 묻고 intent 를 `sdlc reopen <id> --to INTENT_DRAFT` 로.
- 정책 충돌을 임의 해소하지 않는다 — `Conflict & open decisions` 에 차단 yes 로 기록.
