# 보안 한계와 강화 계획 (AT-16)

이 하네스는 **로컬 MVP** 다. 아래 통제는 "실수와 지름길을 막는" 수준이며, 같은 사용자 권한으로 돌아가는 의도적인 우회까지 막지는 못한다. 최종 강제력은 신뢰 가능한 CI · 보호 브랜치 · 조직 승인 시스템에 두어야 한다 (설계서 §9).

## 1. 통제 계층과 각각의 한계

| 계층 | 구현 | 막는 것 | 우회 경로 (확인됨/예상) |
|---|---|---|---|
| Skill/Agent 지침 | `SKILL.md`, `agents/*.md` | 정상 경로의 역할 혼동 | 지침은 소프트 제약 — 모델이 어길 수 있음 |
| Agent `tools` 제한 | qc-verifier·release-auditor 에 Write/Edit 없음 | 직접 파일 편집 | Bash 로 파일 쓰기 가능. 상위 에이전트가 대신 쓸 수 있음 (설계서 §4) |
| PreToolUse 가드 훅 | `scripts/hooks/guard_paths.py` | Edit/Write 로 잠긴 오라클·state·evidence 수정, 경로가 드러난 셸 쓰기 | **확인된 우회**: 경로를 문자열로 조립하는 스크립트(`python3 rewrite.py`), 변수·글롭 사용, 훅 미설치 세션. `tests/test_acceptance.py::AT16` 이 이 우회를 실제로 재현한다 |
| 결정적 검증 | `sdlc validate`/`gate`/`ci` | 기준선 드리프트, 오라클 변조·삭제·skip, 가짜 승인 레코드, 오래된 증거, 계획 밖 변경 | 같은 사용자가 `state.json` 의 기준선·잠금 해시까지 함께 고치면 로컬 검사는 일관된 상태로 보인다 → **CI 에서 PR diff 로 잡아야 함** |
| 로컬 승인 서명 | `sdlc approve` (TTY + 프로젝트 밖 HMAC 키) | 에이전트가 승인 레코드를 손으로 쓰는 것 | 키 파일은 같은 사용자가 읽을 수 있음. 의사 TTY(`script`, `expect`)로 TTY 확인 우회 가능 → 그래서 **E1 등급**이며 high-risk·release 게이트에서는 불인정 |
| 외부 승인 검증기 | `GitHubReviewVerifier` | — | **미구현**. 항상 UNVERIFIABLE → MANUAL_VERIFICATION_REQUIRED (fail-closed) |
| CI 워크플로 | `.github/workflows/sdlc-validate.yml` | PR 단위 검증, QC 자산 변경 시 라벨 리뷰 요구 | required status check·CODEOWNERS·라벨 권한을 운영자가 설정해야만 강제됨 (`docs/branch-protection.md`) |

## 2. 하지 않는 것 (MVP 범위 밖)

- 자동 프로덕션 배포·롤백·외부 메시지 발송 — 명령 자체가 없다. `sdlc deploy` 는 승인 경로만 안내하고 실패한다.
- 실제 승인자 권한·PR 커밋 일치 확인 (M2 GitHub 연동).
- 비밀정보 마스킹: RUN 로그는 명령 출력을 그대로 저장한다. **QC 명령이 비밀값을 출력하지 않게** 해야 한다. `.sdlc/changes/*/evidence/` 를 외부로 반출하기 전 검토가 필요하다.

## 3. 강화 계획 (권장 순서)

1. **보호 브랜치 + required check**: `sdlc-validate` 를 필수 체크로, `.sdlc/changes/*/test-spec.md`·`qc-manifest.json`·`qc-tests/`·`state.json` 에 CODEOWNERS(QA 책임자) 지정. 승인 후 새 커밋 시 리뷰 무효화(dismiss stale reviews) 켜기.
2. **역할별 작업공간 분리**: Builder 는 별도 worktree/컨테이너에서 `.sdlc/` 를 읽기 전용 마운트. QC Verifier 는 `sdlc qc run --isolated` 로 HEAD 고정 worktree 에서 실행.
3. **승인 원본 외부화**: `approvals[scope]` 에 PR 리뷰 ID 를 기록하고 GitHub API 로 승인자 권한·리뷰 시점 SHA 를 검증하는 `GitHubReviewVerifier` 구현 (M2).
4. **CI 에서 기준선 재계산**: PR 의 base 브랜치 `state.json` 과 head 의 기준선 해시를 비교해, 기준선이 승인 없이 함께 바뀌었으면 실패.
5. **조직 관리 설정**: managed settings 로 가드 훅을 강제 설치하고 프로젝트 수준 해제를 막는다.
6. 배포 자격 증명은 에이전트 세션·이 워크플로에 절대 주지 않는다.
