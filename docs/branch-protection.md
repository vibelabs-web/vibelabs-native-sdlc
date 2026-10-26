# 브랜치 보호 · CODEOWNERS 권장 설정 (적용은 별도 승인 후)

이 문서는 **권장안**이다. 실제 GitHub 설정 변경은 리포지터리 관리자가 승인 후 수행한다 (작업지시서 Phase 4-3). 이 하네스는 원격 설정을 바꾸지 않는다.

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
/.github/workflows/                  @<repo-admin>
```

## 3. 라벨

`qc-oracle-approved` 라벨은 QA 책임자만 붙일 수 있게 권한(triage 이상)을 제한한다. 워크플로는 QC 자산이 바뀐 PR 에서 이 라벨이 없으면 실패한다.

## 4. 배포

- 배포 워크플로는 별도 environment(`production`)에 **required reviewers** 를 두고, 배포 자격 증명은 그 environment secret 으로만 노출한다.
- 에이전트 세션·`sdlc-validate` 워크플로에는 배포 자격 증명을 주지 않는다.
