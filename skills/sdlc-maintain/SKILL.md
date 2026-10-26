---
name: sdlc-maintain
description: SDLC 하네스 7단계 — 운영 인시던트를 incident.md 로 기록하고 새 Intent·회귀 TC·담당자로 연결(폐루프)한다. 스킬/훅/CLAUDE.md 변경 시 sdlc eval 로 행동 회귀를 확인한다.
---

# sdlc-maintain — Monitor & Learn

> CLI: `sdlc` = `python3 "${SDLC_HOME:-${CLAUDE_SKILL_DIR}/../..}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

**입력**: 운영 지표·알림·사용자 티켓 (읽기 전용 분석) · **출력**: `incident.md`, 새 변경(CHG), eval-case

## 인시던트 폐루프 (G7)

1. `sdlc draft <id> incident` → 관측/영향/타임라인/원인(증거와 확신 수준 분리)/복구.
2. `Prevention and loop closure` 의 `새 Intent ID`, `새 REQ/TC/EVAL 링크`, `담당자/완료 기준` 을 채운다 — 비어 있으면 `MONITORING → INTENT_DRAFT` 게이트가 막는다.
3. 새 요구는 `sdlc new --title … --source INC-…` 로 별도 변경을 만든다.
4. 재발 방지 TC 는 그 변경의 qc-design 단계에서 추가한다.

## 하네스 자체 회귀

- 스킬(`skills/*/SKILL.md`)·에이전트·훅·CLAUDE.md 를 고쳤으면 `sdlc eval` 실행. 자동 항목 전부 PASS + 수동 항목(EVAL-001/002/007/014)은 전사로 판정.
- 운영 실데이터·고객 정보는 eval 에 넣지 않는다 (개인정보 제거 후 수집).
