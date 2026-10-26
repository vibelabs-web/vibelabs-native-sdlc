---
name: sdlc-release
description: SDLC 하네스 6단계 — QC_PASSED 이후 review.md·release.md 체크리스트와 위험 요약 초안만 작성한다. 배포·승인·외부 전송은 하지 않으며 RELEASE_APPROVED 는 외부 승인 시스템 없이는 통과하지 않는다.
---

# sdlc-release — PR Review & Release 체크리스트

> CLI: `sdlc` = `python3 "${SDLC_HOME:-$HOME/.claude/skills/sdlc}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

**입력**: qc-report, 전체 diff, plan·승인 기록 · **출력**: `review.md`, `release.md` (초안) · **에이전트**: `sdlc-release-auditor`
**종료 조건**: 체크리스트 작성 + 사람에게 승인 경로 안내

## 절차

1. `sdlc gate <id> REVIEW_PENDING` (QC 증거가 여전히 현재 HEAD 와 일치해야 함).
2. `sdlc release <id>` → review.md/release.md 생성. 사전 점검 결과(RELEASE_APPROVED = MANUAL)를 그대로 보고.
3. 검토 축: (A) plan 대비 diff 불일치 (B) spec/TC 충족도 (C) 위험 범주와 필요한 승인자 (D) 비밀정보·의존성·롤백 준비.
4. 미확인 항목은 '미확인' 으로 둔다. 승인자·시각을 지어내지 않는다.

## 금지

- `sdlc deploy` 외의 어떤 배포·롤백·태그 푸시도 실행하지 않는다 (`sdlc deploy` 는 안내 후 실패).
- 승인을 대리하지 않는다. production 은 지정된 인간 승인 + CI 권한에서만.
