# 브랜치 보호 · CODEOWNERS 권장 설정 (적용은 별도 승인 후)

이 문서는 **권장안**이다. 실제 GitHub 설정 변경은 리포지터리 관리자가 승인 후 수행한다 (작업지시서 Phase 4-3). 이 하네스는 원격 설정을 바꾸지 않는다.

## 0. 이 레포의 현재 상태 (2026-10-26)

- `vibelabs-web/vibelabs-native-sdlc` 는 **무료 플랜 비공개 레포**라 GitHub 가 브랜치 보호·규칙셋을 허용하지 않는다
  (`PUT …/branches/main/protection` → HTTP 403 "Upgrade to GitHub Pro or make this repository public").
- 작가님 결정: 비공개 유지, 보호 없이 운영. 대신
  - 모든 변경은 브랜치 → PR → `validate` 체크 성공 확인 → 머지 순서로 한다 (운영 규칙 — 강제력 없음).
  - `.github/CODEOWNERS` 는 두되 리뷰 강제는 꺼져 있다.
- Pro 업그레이드나 공개 전환 시 아래 §1 설정을 그대로 적용한다. 1인 계정일 때는 승인 수 0·코드오너 리뷰 끔으로 시작한다
  (GitHub 는 자기 승인을 막으므로 승인 1 이상이면 아무도 머지할 수 없다).

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

`qc-oracle-approved` 라벨은 QA 책임자만 붙일 수 있게 권한(triage 이상)을 제한한다. 워크플로는 QC 자산이 바뀐 PR 에서 이 라벨이 없으면 실패한다.

## 4. 배포

- 배포 워크플로는 별도 environment(`production`)에 **required reviewers** 를 두고, 배포 자격 증명은 그 environment secret 으로만 노출한다.
- 에이전트 세션·`sdlc-validate` 워크플로에는 배포 자격 증명을 주지 않는다.
