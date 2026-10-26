# 브랜치 보호 · CODEOWNERS 권장 설정 (적용은 별도 승인 후)

이 문서는 **권장안**이다. 실제 GitHub 설정 변경은 리포지터리 관리자가 승인 후 수행한다 (작업지시서 Phase 4-3). 이 하네스는 원격 설정을 바꾸지 않는다.

## 0. 이 레포의 현재 상태 (2026-10-26)

- 처음엔 무료 플랜 비공개라 보호 API 가 403("Upgrade to GitHub Pro or make this repository public")이었다.
- 같은 날 작가님 결정으로 **공개 전환** 후 `main` 에 보호를 적용했다:
  - PR 필수, **승인 수 0** — 1인 계정이라 GitHub 가 자기 승인을 막아 1 이상이면 아무도 머지할 수 없다. SDLC 변경의 승인은 하네스 게이트(봇 리뷰 E2)가 따로 검증한다.
  - 필수 체크 `validate` + 최신 base 반영 필수(strict)
  - 관리자에게도 적용(enforce_admins), force push·삭제 금지
  - 코드오너 리뷰 강제는 끔(`.github/CODEOWNERS` 는 표시용)
- 확인: `gh api repos/vibelabs-web/vibelabs-native-sdlc/branches/main/protection`

## 1. 보호 브랜치 (`main`)

- Require a pull request before merging — 승인 1명 이상, **Dismiss stale pull request approvals when new commits are pushed** 켜기 (승인 후 코드가 바뀌면 승인 무효 — AT-06 과 같은 원칙)
- Require review from Code Owners
- Require status checks to pass: `sdlc-validate / validate`, Require branches to be up to date
- Do not allow bypassing the above settings (관리자 포함)
- Restrict force pushes / deletions

## 2. CODEOWNERS 예시

```text
# QC 오라클과 상태는 QA 책임자 리뷰 필수
/.sdlc/changes/*/test-spec.md        @<qa-lead>
/.sdlc/changes/*/qc-manifest.json    @<qa-lead>
/.sdlc/changes/*/qc-tests/           @<qa-lead>
/.sdlc/changes/*/state.json          @<qa-lead> @<tech-lead>
/.sdlc/changes/*/spec.md             @<product-owner>
/.sdlc/policies/                     @<repo-admin> @<security-owner>
/.github/workflows/                  @<repo-admin>
```

## 3. 라벨

`qc-oracle-approved` 라벨은 QA 책임자만 붙일 수 있게 권한(triage 이상)을 제한한다. 워크플로는 QC 자산이 바뀐 PR 에서 이 라벨도, base 정책에 등록된 승인자의 유효한 리뷰도 없으면 실패한다 (`scripts/ci/check_qc_assets.py`).

## 4. 배포

- 배포 워크플로는 별도 environment(`production`)에 **required reviewers** 를 두고, 배포 자격 증명은 그 environment secret 으로만 노출한다.
- 에이전트 세션·`sdlc-validate` 워크플로에는 배포 자격 증명을 주지 않는다.
