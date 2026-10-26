# 데모 따라하기 — 행사 신청 30명 + 대기자 자동 승격 (10~15분)

새 개발자가 빈 디렉터리에서 intent → QC 통과 → 리뷰 체크리스트까지 한 바퀴 도는 절차다.
이 명령들은 2026-10-26 에 깨끗한 임시 디렉터리에서 그대로 실행해 확인했다 (승인 단계는 아래 '확인 방법' 참고).

## 준비

```bash
H=/path/to/vibelabs-native-sdlc            # 이 레포
sdlc() { python3 "$H/scripts/sdlc.py" "$@"; }
mkdir sdlc-demo && cd sdlc-demo
git init -q && git config user.name "<이름>" && git config user.email "<메일>"
sdlc demo-init --change-id CHG-DEMO-001
git add -A && git commit -qm "demo init"
sdlc inspect CHG-DEMO-001
```

`demo-init` 은 `examples/event-registration/` 을 **복사**해 `app/`(데모 구현·Builder 자체 테스트)과
`.sdlc/changes/CHG-DEMO-001/`(intent·spec·plan·test-spec·qc-manifest·qc-tests)을 만든다. 원본 예시는 바뀌지 않는다.
REQ-004(중복 신청)는 미결정이라 TC 가 없다 — 정하지 않은 정책에는 합격 기준을 만들지 않는다.

## 1. Intent → Spec → Plan + Test Spec

`approve` 는 **사람이 직접 터미널에서** 실행한다(TTY 확인 · 변경 ID 를 입력해야 기록됨). 에이전트·파이프로는 거부된다.

```bash
sdlc approve CHG-DEMO-001 intent          # 'CHG-DEMO-001' 입력
sdlc gate CHG-DEMO-001 INTENT_APPROVED    # ALLOW (exit 0)
sdlc gate CHG-DEMO-001 SPEC_DRAFT
sdlc approve CHG-DEMO-001 spec
sdlc gate CHG-DEMO-001 SPEC_APPROVED
sdlc gate CHG-DEMO-001 PLAN_TEST_DRAFT
sdlc validate CHG-DEMO-001 --strict       # errors=0 blockers=0 trace_coverage=1.0
sdlc approve CHG-DEMO-001 plan_test
sdlc gate CHG-DEMO-001 BASELINE_APPROVED  # 이 순간 test-spec·qc-manifest·qc-tests 가 해시로 잠긴다
```

승인 없이 게이트를 부르면 `MANUAL_VERIFICATION_REQUIRED`(exit 3), 단계를 건너뛰면 `INVALID_TRANSITION`(exit 1) 이다.

## 2. Build → QC

```bash
sdlc gate CHG-DEMO-001 BUILDING
sdlc build check CHG-DEMO-001 -- python3 -m unittest discover -s app   # Builder 자체 검사, exit 0
sdlc gate CHG-DEMO-001 QC_RUNNING
sdlc qc run CHG-DEMO-001 --isolated       # 임시 worktree 에서 HEAD 고정 실행 → RUN-001
sdlc report CHG-DEMO-001                  # verified_coverage=1.0, traceability.md·qc-report.md 생성
sdlc gate CHG-DEMO-001 QC_PASSED
```

확인할 것: `.sdlc/changes/CHG-DEMO-001/evidence/RUN-001.json` 의 `commit_sha`·`spec_sha`·`test_spec_sha`·`report_sha256`, TC 별 로그.

## 3. 리뷰 체크리스트 (배포 없음)

```bash
sdlc gate CHG-DEMO-001 REVIEW_PENDING
sdlc release CHG-DEMO-001                 # review.md·release.md 초안, RELEASE_APPROVED 사전 점검 = MANUAL
sdlc deploy CHG-DEMO-001                  # 승인 경로 안내만 하고 exit 1
```

RELEASE_APPROVED 는 외부 승인 시스템(E2) 검증이 필요해서 로컬 승인으로는 통과하지 않는다. 여기서 데모가 끝난다.

## 4. 실행 중 실패가 나오면 — 디버깅 순서

QC 에서 FAIL 이 나오면 하네스가 `issues/BUG-NNN.md` 를 자동으로 만든다. 아래 순서로 처리한다.

1. **재현**: BUG 파일의 commit SHA·명령·로그(`evidence/RUN-NNN/TC-xxx.log`)로 같은 실패를 다시 본다.
   ```bash
   sdlc gate CHG-DEMO-001 DEFECT_OPEN && sdlc gate CHG-DEMO-001 BUILDING
   sdlc bug transition CHG-DEMO-001 BUG-001 --to triaged --role builder
   sdlc bug transition CHG-DEMO-001 BUG-001 --to in_progress --role builder
   ```
2. **원인 지점 특정**: 기대값(test-spec 의 Then)과 실제값을 비교해 어느 코드 경로인지 좁힌다. QC 테스트는 고치지 않는다.
3. **수정**: 제품 코드만 고치고 커밋한다.
4. **재발하지 않는지 확인**: 자체 검사 → QC 재실행. `verified_fixed` 는 QC 만 판정한다.
   ```bash
   sdlc bug transition CHG-DEMO-001 BUG-001 --to ready_for_retest --role builder
   sdlc build check CHG-DEMO-001 -- python3 -m unittest discover -s app
   sdlc gate CHG-DEMO-001 QC_RUNNING && sdlc qc run CHG-DEMO-001 --isolated   # RUN-002, 전체 TC 재실행
   ```
   같은 SHA 로 재실행하면 verified_fixed 가 되지 않는다. 수정 시도가 3번 실패하면 `escalated` 가 되고 자동 루프가 멈춘다 — 사람이 결정한다.

## 확인 방법 (문서 작성자가 한 검증)

- 위 명령 전체를 빈 디렉터리에서 실행: 모든 게이트 ALLOW, RUN-001 전 TC PASS, RELEASE_APPROVED = MANUAL, deploy exit 1.
- 승인 단계는 사람 대신 Python `pty` 로 의사 TTY 를 만들어 입력했다. 이것은 `docs/security-limitations.md` 에 적은 **알려진 우회 경로**이며, 그래서 로컬 승인은 E1 등급으로만 취급된다.
- 결함 루프(§4)는 `tests/test_acceptance.py::AT10_FixAndRegression` 이 회귀 픽스처로 자동 검증한다.
