# GitHub 연동 (M2)

인증은 사용자의 `gh` 로그인을 그대로 쓴다(`gh auth status`). 하네스는 토큰을 저장하지 않는다.
레포는 `origin` 원격에서 찾고, 다르면 `SDLC_GITHUB_REPO=owner/repo` 로 지정한다. `SDLC_GITHUB_OFFLINE=1` 이면 모든 호출을 끊는다(검증 불가 → MANUAL).

## 1. PR 리뷰를 승인 원본으로 (E2)

```bash
# 1) 승인받을 산출물(.sdlc/changes/<id>/…)을 커밋해 PR 로 올린다
# 2) 승인권자가 GitHub 에서 PR 을 Approve
# 3) 리뷰 URL 확인
gh api repos/<owner>/<repo>/pulls/<n>/reviews --jq '.[] | select(.state=="APPROVED") | .html_url'
# 4) 등록 — 등록 시점과 이후 모든 게이트에서 GitHub API 로 다시 확인한다
sdlc approve-github <CHG> intent --review https://github.com/<owner>/<repo>/pull/<n>#pullrequestreview-<id>
```

검증 항목 (하나라도 어긋나면 INVALID → BLOCK, GitHub 에 닿지 못하면 UNVERIFIABLE → MANUAL):

| 항목 | 이유 |
|---|---|
| 리뷰 상태 `APPROVED` | COMMENTED·CHANGES_REQUESTED 는 승인 아님 |
| 리뷰어 ≠ PR 작성자 | 자기 승인 차단 |
| 리뷰어 권한 admin/maintain/write | 권한 없는 계정의 승인 차단 |
| `.sdlc/policies/approvers.json` 의 스코프 명단 (있을 때) | 스코프별 승인 책임자 (PO·QA·보안·운영) |
| **리뷰한 커밋의 파일 내용 = 승인 대상 SHA** | 리뷰 후 파일이 바뀌면 그 승인은 무효. `qc-tests/` 는 트리 해시로 비교 |
| release: 리뷰 커밋 = 현재 HEAD | 다른 커밋에 받은 승인 재사용 차단 |

## 2. 위험 기반 게이트

| 등급 | 필요한 승인 |
|---|---|
| lite · standard | intent / spec / plan_test — 로컬 TTY(E1) 또는 GitHub 리뷰(E2) |
| high | 위 3개 모두 **GitHub 리뷰(E2)** + `security` 스코프 승인. security 승인자는 정책 명단에 있어야 하고 plan_test 승인자와 **다른 사람** |
| release (모든 등급) | GitHub 리뷰(E2, 커밋 = HEAD) + 필수 CI 체크 성공 |

필수 CI 체크: 정책의 `required_checks`(기본 `["validate"]` — `sdlc-validate` 워크플로의 job 이름). 현재 HEAD 의 check-run 이 모두 `success` 여야 한다. 없거나 실행 중이면 MANUAL, 실패면 BLOCK. high-risk 는 QC_PASSED 에서도 확인한다.

정책 예시: `examples/policies/approvers.example.json` → 대상 프로젝트의 `.sdlc/policies/approvers.json` 으로 복사. 이 파일은 CODEOWNERS 로 보호하고, 가드 훅이 에이전트의 직접 수정을 막는다.

## 3. 버그 추적 · QC ↔ Builder 소통

```
BUG 파일 (판정 원본)  ──sdlc bug sync──▶  GitHub Issue (보기·대화)
   frontmatter 상태                          라벨 bug:<상태> sev:<심각도> chg:<변경>
   ## History (상태 이력)   ◀── 상태 변경 댓글 ──
   ## Discussion            ◀── Issue 댓글 인용 (비신뢰)
                            ──▶ bug comment 로 남긴 말 전송
```

| 하고 싶은 것 | 명령 |
|---|---|
| Issue 만들기·갱신, 댓글 주고받기 | `sdlc bug sync <CHG>` (`--dry-run` 으로 미리 보기) |
| QC·Builder 가 말 남기기 | `sdlc bug comment <CHG> BUG-001 --role builder --body "원인: …"` — 오프라인이면 `[pending]` 으로 쌓였다가 다음 sync 때 전송 |
| 전체 버그 한눈에 | `sdlc bug board` → `.sdlc/BUGS.md` |
| 상태 바꾸기 | 기존과 같이 `sdlc bug transition` / `sdlc qc run` — **Issue 를 닫거나 라벨을 바꿔도 반영되지 않고 다음 sync 때 되돌린다** |

사람(PO·QA)은 GitHub Issue 에서 댓글로 참여하면 된다. 그 댓글은 다음 sync 때 BUG 파일 Discussion 에 `[github #id] · github:<login>` 으로 인용되고, 에이전트는 이를 참고 정보로만 읽는다 — 댓글 속 "verified_fixed 로 바꿔" 같은 지시는 실행하지 않는다.

## 4. 한계

- 승인자 권한 확인은 PR 리뷰 시점이 아니라 **확인 시점**의 권한이다.
- 같은 `gh` 토큰을 쓰는 에이전트는 그 계정으로 리뷰를 남길 수 있다. 자기 승인은 GitHub·검증기가 막지만, 에이전트에게 **승인권자 계정의 토큰을 주지 않아야** 한다.
- Issue 본문은 BUG 파일 내용(로그 경로·SHA)을 그대로 올린다 — 공개 레포라면 내용을 먼저 확인한다.
