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

## 5. 완전 자율 모드 (사람 승인 0)

작가님 결정(2026-10-26): 모든 작업과 PR 을 AI 에이전트가 맡고, 승인도 사람 없이 진행한다.
계정이 하나면 GitHub 는 자기 PR 승인을 막으므로, **승인 리뷰만 별도 기계 신원(GitHub App 봇)** 으로 남긴다.

### 한 번만 하는 설정

```bash
sdlc github-app setup        # 브라우저가 열리면 'Create GitHub App' 클릭 (권한: PR write, contents/checks read)
#  → https://github.com/apps/<slug>/installations/new 에서 이 레포에 설치
cp examples/policies/approvers.autonomous.example.json .sdlc/policies/approvers.json   # <app-slug> 치환
sdlc github-app status       # 설치 토큰 발급·정책 명단 확인
```

키는 `~/.config/vibelabs-sdlc/app-<slug>.pem`(0600), 설정은 `app.json` — 레포 밖이다.

### 승인 규칙 (`sdlc auto-approve <CHG> <scope> --pr N`)

봇은 아래가 **모두** 참일 때만 PR 을 Approve 한다. 하나라도 아니면 리뷰를 남기지 않는다.

1. 대상 게이트 dry-run 결과 error·blocker 0
2. 남은 MANUAL 사유가 "이 스코프(와 plan_test↔security 짝)의 승인 레코드 없음" 뿐 — CI 미완료·GitHub 불가 등은 거부(exit 3)
3. PR 이 열려 있고 PR head == 로컬 HEAD (승인 대상이 push 됨)
4. 리뷰 후 검증기 재확인 통과 (봇이 정책 명단에 있음, 리뷰 커밋 내용 = 승인 대상 SHA)

### 에이전트 흐름

1. `sdlc new` → 브랜치 `sdlc/<CHG>` → 산출물 커밋·push → PR 생성
2. 단계마다: 담당 에이전트가 산출물 작성 → 커밋·push → `sdlc-gatekeeper` 가 `auto-approve` → `sdlc gate`
3. Build·QC 커밋 push → CI `validate` 성공 → QC_PASSED → REVIEW_PENDING
4. `auto-approve release`(CI 성공 필수) → `gate RELEASE_APPROVED` → PR 머지

### CI 의 QC 자산 검사 (자율 모드)

PR 이 `test-spec.md`·`qc-manifest.json`·`qc-tests/` 를 바꾸면 `scripts/ci/check_qc_assets.py` 가 다음 중 하나를 요구한다.
- `qc-oracle-approved` 라벨 (사람 QA 모드), 또는
- **base 브랜치(main) 정책**의 plan_test 명단에 있는 계정(봇)의 APPROVED 리뷰 + 그 리뷰 커밋 이후 QC 자산 변경 없음

정책을 base 에서 읽으므로 **정책 파일은 QC 자산과 다른 PR 로 먼저 main 에 들어가 있어야 한다** (PR 이 스스로 넣은 정책으로 자기 승인 불가).
봇 리뷰가 제출되면 `pull_request_review` 이벤트로 CI 가 다시 돌고, 게이트는 같은 커밋의 **가장 최근** 체크 결과를 본다.

### 이 모드에서 사라지는 것 / 남는 것

- 사라짐: 사람의 판단. "승인"은 결정적 규칙(추적성·오라클 잠금·증거·CI)이 모두 통과했다는 기록이 된다.
  요구사항이 사용자 의도와 맞는지는 규칙이 판정하지 못한다 — intent 의 OPEN 질문은 여전히 차단(blocker)으로 남아 에이전트가 멈춘다.
- 남음: 자기 승인 차단(봇 ≠ PR 작성자), 리뷰 후 내용 변경 시 승인 무효, 오래된 증거 거부, 재시도 예산 초과 시 escalated(사람 없이는 해제 불가 — 이 모드에서도 멈춘다).
- 독립성 한계: 봇 키는 같은 머신 같은 사용자 권한에 있다. Builder 에이전트가 키 파일을 읽어 봇으로 직접 리뷰하는 것을 기술적으로 막지는 못한다.
  규칙 2·4 가 우회 리뷰를 걸러 주지만(차단 사유가 있으면 검증기·게이트가 다시 막음), 키를 분리된 환경(CI 시크릿 등)으로 옮기는 것이 다음 강화 단계다.
