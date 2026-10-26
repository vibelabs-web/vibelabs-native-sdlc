---
name: sdlc-qc-run
description: SDLC 하네스 5단계 — Builder 와 분리된 컨텍스트에서 고정 커밋 SHA 로 qc-manifest 를 실행(sdlc qc run --isolated)해 RUN 증거를 남기고, 실패는 BUG 로 발행하며, QC_PASSED 또는 DEFECT_OPEN 게이트를 판정한다. 제품 코드는 고치지 않는다.
---

# sdlc-qc-run — QC & Defect Loop

> CLI: `sdlc` = `python3 "${SDLC_HOME:-$HOME/.claude/skills/sdlc}/scripts/sdlc.py"` — 대상 프로젝트 루트에서 실행. 공통 규칙은 `/sdlc` 진입 스킬 §3.

**입력**: 고정 HEAD, 잠긴 spec·test-spec·qc-tests · **출력**: `evidence/RUN-NNN.json`·로그, `issues/BUG-NNN.md`, `qc-report.md`, `traceability.md` · **에이전트**: `sdlc-qc-verifier`
**종료 조건**: `sdlc gate <id> QC_PASSED` = ALLOW, 또는 `DEFECT_OPEN` 으로 Builder 에 반환

## 절차

1. 새 컨텍스트에서 시작한다. Builder 의 요약·대화는 증거가 아니다 — 받으면 무시하고 아래를 실행.
2. `sdlc inspect <id>` → stage QC_RUNNING 확인.
3. `sdlc qc run <id> --isolated` (임시 worktree 에서 HEAD 고정 실행). 결과: PASS / FAIL / NOT_RUN(skip·0건) / BLOCKED(INFRA).
4. FAIL 은 자동으로 BUG 발행·재오픈된다. 출력의 bug_events 를 그대로 보고.
   Builder 에게 전할 관찰(재현 조건·로그 위치)은 `sdlc bug comment <id> BUG-NNN --role qc-verifier --body "…"`,
   GitHub 원격이 있으면 `sdlc bug sync <id>` 로 Issue 에 반영.
5. `sdlc report <id>` → verified_coverage 와 REQ 별 판정 확인.
6. 독립 도전: 고정 TC 외 반례(경쟁조건·경계·고정 seed 무작위)를 시도할 수 있다. 새 반례는 **재현성과 기대값이 spec 으로 확인된 뒤** `sdlc bug new` 로 발행하고, 회귀 자산 승격은 QC Architect 가 reopen 절차로.
7. 결함이 있으면 `sdlc gate <id> DEFECT_OPEN`, 없으면 `sdlc gate <id> QC_PASSED`.

## 판정 규칙

- NOT_RUN·BLOCKED 는 PASS 가 아니다. 환경 오류는 `sdlc bug classify … infra`, 불안정은 `flaky`, 오라클 의심은 `oracle` → 사람에게.
- 이전 SHA 의 RUN 을 재사용하지 않는다 (STALE_EVIDENCE_SHA).
- 제품 코드·QC 오라클을 수정하지 않는다. Write/Edit 도구를 쓰지 않는다.
