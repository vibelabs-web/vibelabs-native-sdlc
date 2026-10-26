# 운영자 가이드

## 1. 명령 요약

| 명령 | 용도 | 종료 코드 |
|---|---|---|
| `new --title T [--risk auto\|lite\|standard\|high] [--source S]` | 변경 생성 (`CHG-YYYYMMDD-NNN`) + intent.md. 보안 키워드는 high 고정, 하향 불가 | 0 |
| `list` / `inspect <id>` | 단계·차단 사유·다음 허용 단계·승인 검증 상태 | 0 |
| `draft <id> <artifact>` | 템플릿에서 초안 (기존 파일 덮어쓰지 않음) | 0/2 |
| `validate <id>\|--all [--strict] [--json]` | 스키마·ID·추적성·기준선 드리프트·오라클 잠금·skip·BUG 스키마 | 0/1 |
| `approve <id> intent\|spec\|plan_test\|release` | **사람 전용 (TTY)** 로컬 승인 E1 | 0/2 |
| `gate <id> <STAGE> [--dry-run] [--json]` | 전이 판정, ALLOW 면 적용 | 0 ALLOW / 1 BLOCK / 3 MANUAL |
| `reopen <id> --to INTENT_DRAFT\|SPEC_DRAFT\|PLAN_TEST_DRAFT --reason R` | 재기준화: 해당 승인·기준선·잠금 제거, 이전 RUN stale | 0/2 |
| `build check <id> -- <cmd>` | Builder 자체 검사 기록 (QC_RUNNING 조건) | 명령 exit |
| `qc run <id> [--isolated] [--allow-dirty]` | 고정 SHA QC 실행 → RUN 증거, BUG 발행·재검증 | 0 전부 PASS / 1 |
| `bug list\|new\|transition\|classify` | 결함 티켓 | 0/2 |
| `report <id>` | traceability.md·qc-report.md 생성, 커버리지 | 0 |
| `drift <id>` | plan.md 대비 계획 밖 변경 | 0/1 |
| `release <id>` | review.md·release.md 초안 (명령 실행 없음) | 0 |
| `deploy` | 미구현·금지 — 승인 경로 안내 | 1 |
| `eval` | 하네스 자체 평가 | 0/1 |
| `ci` | `validate --all` (CI 진입점) | 0/1 |

## 2. 상태 기계 (SOP §3)

```
INTAKE → INTENT_DRAFT → INTENT_APPROVED* → SPEC_DRAFT → SPEC_APPROVED* → PLAN_TEST_DRAFT → BASELINE_APPROVED*
→ BUILDING → QC_RUNNING → {DEFECT_OPEN → BUILDING | QC_PASSED → REVIEW_PENDING → RELEASE_APPROVED** → MONITORING}
(* 로컬 E1 승인 가능 — high-risk 제외 · ** 외부 E2 승인 필수, 로컬 MVP 에서는 항상 MANUAL)
```

## 3. 게이트가 보는 것

| 대상 단계 | 조건 |
|---|---|
| 모든 단계 | 허용된 전이, 구조 error 0, 이전 승인 전부 VERIFIED + 묶인 SHA 일치 |
| INTENT_APPROVED | intent 필수 섹션·자리표시자 0·차단 OPEN 0, intent 승인 |
| SPEC_APPROVED | spec 의 REQ 원천·자리표시자 0, spec 승인 |
| BASELINE_APPROVED | 모든 must REQ 에 TASK·TC·qc-manifest 명령, 미결정 REQ 에 TC 없음, plan_test 승인 → 기준선·QC 잠금 기록 |
| QC_RUNNING | git HEAD, `.sdlc/` 밖 미커밋 0, 현재 HEAD 의 build check exit 0, 계획 밖 변경 0 |
| DEFECT_OPEN | 미해결 BUG ≥ 1 |
| BUILDING (from DEFECT_OPEN) | escalated/blocked_spec BUG 가 있으면 MANUAL |
| QC_PASSED · REVIEW_PENDING | 최신 RUN 무결(report_sha256·로그 해시) · commit = HEAD · 기준선 일치 · dirty 아님 · 모든 must TC = PASS · 미해결 BUG 0 |
| RELEASE_APPROVED | 위 + release 승인 E2 (외부) |
| INTENT_DRAFT (from MONITORING) | incident.md 의 새 Intent·REQ/TC/EVAL·담당자 채워짐 |

## 4. 증거 등급

E0 AI 진술만 (게이트 불가) · E1 로컬 명령 로그/로컬 TTY 승인 · E2 신뢰 CI 실행·외부 승인 (미구현) · E3 독립 재현 환경.
`sdlc qc run` 증거는 E1 이다. 사용자 합격 결정에는 E2 이상을 권고한다 (설계서 §5.4).

## 5. 사람을 부르는 시점 (SOP §8)

게이트가 MANUAL 을 내면 사람의 차례다: 승인, escalated 결함 결정, oracle/flaky/infra 분류된 BUG, high-risk 변경, 배포.
escalated·blocked_spec 해제는 `sdlc bug transition … --to triaged --role human --note "<결정>"` 을 TTY 에서.

## 6. 파일 위치

```
.sdlc/changes/CHG-…/
  state.json            # CLI 전용 — 단계·기준선·승인·잠금·이력
  intent.md spec.md plan.md test-spec.md qc-manifest.json qc-tests/
  traceability.md qc-report.md review.md release.md   # 자동 생성 초안
  build/BUILD-NNN.log   evidence/RUN-NNN.json + RUN-NNN/TC-*.log   issues/BUG-NNN.md
```
