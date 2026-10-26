# 구현 결정 기록 (설계서와 다르거나 설계서가 정하지 않은 것)

| # | 결정 | 설계서 원안 | 이유 |
|---|---|---|---|
| D1 | 레포 루트가 `/sdlc` 스킬, `skills/sdlc-*`·`agents/sdlc-*` 를 `install.sh` 로 `~/.claude` 에 심링크 | `.claude/skills/…`, `.claude/agents/…` (§3) | 작가님 결정 — 다른 프로젝트에서도 `/sdlc` 사용. 같은 레포의 다른 스킬(storm-research) 관례와 일치 |
| D2 | 에이전트 이름에 `sdlc-` 접두사 | `planner`, `builder` … | `~/.claude/agents` 의 기존 에이전트와 충돌 방지 (repository-audit §2) |
| D3 | Python 3 표준 라이브러리만 사용, JSON Schema 는 부분 구현 | 미정 | 설치 없이 실행, CI 단순화 |
| D4 | 기준선 해시 = git blob SHA(40자)를 Python 으로 직접 계산 | `*_git_sha` | git 없는 환경·미커밋 파일에도 동일 값. `git hash-object` 와 일치 (tests) |
| D5 | 승인은 `state.json.approvals[scope]` 레코드만 신뢰, 문서 frontmatter `status`/`approval_ref` 는 무시(경고만) | §5.3 | AT-14 — 문자열 기입은 승인이 아님 |
| D6 | 로컬 승인 `local_attested`: TTY 확인 + 프로젝트 밖 HMAC 키 서명, 등급 E1. standard/lite 의 intent·spec·plan_test 게이트에만 인정 | "오프라인은 manual_verification_required" | 완전 fail-closed 면 로컬 데모가 진행 불가. 대신 high-risk·release 는 E2 필수로 항상 MANUAL |
| D7 | 승인 스코프는 SHA 에 묶임: intent=[intent], spec=[intent,spec], plan_test=[spec,plan,test_spec,qc_manifest,qc_tests], release=[commit,qc_run] | §5.3 approvals | 승인 후 파일이 바뀌면 자동 무효 (AT-06) |
| D8 | TC ↔ 실행 명령을 `qc-manifest.json`(QC 소유)으로 분리 | test-spec "수행 환경/정확한 명령" 서술 | 기계 실행·잠금 가능하게. test-spec 은 사람용 오라클로 유지 |
| D9 | QC 소유 테스트 위치 `.sdlc/changes/<id>/qc-tests/`, BASELINE_APPROVED 시 해시 잠금(`state.qc_lock`) | "별도 소유 경로" | 경로 하나로 훅·CI·CODEOWNERS 를 모두 걸 수 있음 |
| D10 | Builder 자체 검사 기록 `sdlc build check` 를 QC_RUNNING 게이트 조건으로 | G4 서술 | "Builder 자체 검사 통과" 전이 조건을 증거로 |
| D11 | dirty 판정은 `.sdlc/` 밖만 | — | 증거·BUG 파일 쓰기가 작업트리를 더럽히지 않게. `.sdlc/` 무결성은 기준선·잠금 해시가 담당 |
| D12 | 판정 심각도 3단계: error(구조 결함) / blocker(미완성) / warning. `validate` 는 error 만 실패, `--strict`·게이트는 blocker 도 실패 | — | 작성 중인 변경이 CI 를 깨지 않도록. 단, 기준선 드리프트·오라클 변조는 error |
| D13 | 아직 작성 단계가 아닌 산출물(plan/test-spec)의 오류는 INTENT/SPEC 승인을 막지 않음 | — | 앞당겨 만든 초안이 앞 단계 승인을 막는 문제 (EVAL-004 개발 중 발견) |
| D14 | 결함 재시도 예산: `ready_for_retest → reopened` 횟수가 `retry_budget.per_defect`(기본 3) 이상이면 `escalated`. 해제는 TTY 사람 결정만 | §6.3 "결함당 3회" | 동일 증상 판정은 "같은 TC 재실패"로 단순화 |
| D15 | `verified_fixed`·`reopened` 는 `sdlc qc run` 만 설정. 실패 SHA 와 같은 SHA 의 PASS 로는 verified_fixed 불가 | SOP 단계 5 | 수정 커밋 없이 종료 방지 |
| D16 | Lite 등급은 기록만 하고 게이트는 Standard 와 동일 | SOP §1 Lite 간소화 | MVP 단순화. 보안 키워드가 있으면 Lite 요청도 high 로 고정 |
| D17 | "데모 문제 주입" 구현 변형은 `evals/fixtures/` 의 **하네스 회귀 픽스처**로만 둔다. 데모 안내서는 실제 흐름 + 디버깅 순서(재현→원인→수정→재발 확인) | 작업지시서 §4 | 작가님 전역 규칙: 교육 자료에 "일부러 깨뜨리기" 실습 금지 |
| D18 | MONITORING 은 로컬에서 도달 불가(release 승인 E2 필요). EVAL-016 은 stage 를 시뮬레이션해 폐루프 게이트만 검증 | — | 배포 경로 미구현 |
| D19 | 데모 `spec.md` 에 공개 계약(Interfaces) 섹션을 덧붙여 복사 | 예시 spec 에 없음 | QC 테스트가 구현 내부가 아니라 spec 계약에만 의존하도록 |
| D20 | `examples/event-registration/plan-with-paths.md` 신규 — 원본 `plan.md` 는 수정하지 않음 | — | 드리프트 검사에 실제 경로가 필요 |
| D21 | GitHub 호출은 `gh api` 에 위임, 토큰 비저장. `SDLC_GITHUB_OFFLINE=1` 로 차단, 테스트는 `set_client()` 주입 | §10 M2 | 사용자 인증 재사용, 의존성 없음, 결정적 테스트 |
| D22 | PR 리뷰 승인은 "리뷰한 커밋의 파일 blob SHA = 승인 대상 SHA" 로 묶는다 (`contents?ref=`, qc-tests 는 트리 해시) | §5.3 "승인자 권한/커밋 일치" | 리뷰 후 바뀐 내용에 승인이 따라가지 않게 |
| D23 | 승인 책임자 명단 `.sdlc/policies/approvers.json` — 없으면 쓰기 권한자 누구나, 있으면 명단만. high-risk 의 `security` 는 명단 필수 | SOP §2 RACI | 조직마다 다른 책임자를 데이터로 |
| D24 | high-risk = 모든 승인 E2 + `security` 별도 승인(plan_test 승인자와 다른 사람) | SOP §1 "추가 보안/정책 소유자 승인" | 1인 승인으로 고위험 변경 통과 차단 |
| D25 | E2 CI 증거 = 현재 HEAD check-run 의 `required_checks` 전부 success. RELEASE_APPROVED 항상, high-risk 는 QC_PASSED 에도 | §5.4 E2 | 로컬 RUN(E1)만으로 릴리스 금지 |
| D26 | 버그 소통은 GitHub Issue 를 거울로, 원본은 BUG 파일. GitHub 쪽 수동 닫기·라벨 변경은 sync 때 되돌린다 | — | Issue 닫기로 결함이 "해결"되는 우회 차단 |
| D27 | Issue 댓글은 BUG Discussion 에 인용(`> `)만, 하네스 자신의 댓글은 `<!-- sdlc-harness -->` 표식으로 구분해 되가져오지 않음 | — | prompt injection 방어, 중복 방지 |
