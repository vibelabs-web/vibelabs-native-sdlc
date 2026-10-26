# Repository Audit — Phase 0 (읽기 전용)

감사일: 2026-10-26 · 감사 방법: 파일 목록·문서 정독·`~/.claude` 설정 조회(쓰기 없음)

## 1. 현행 상태

| 항목 | 관찰 |
|---|---|
| 언어/런타임 | 코드 없음. 로컬 `python3` 3.14 / `git` 2.53 사용 가능 |
| 테스트/CI | 없음 (`tests/`, `.github/` 부재) |
| CLI 엔트리포인트 | 없음 |
| git | `968931b Initial commit`(빈 커밋). 모든 파일이 untracked |
| `.claude/` | 이 레포에 없음. README가 언급한 `.claude/skills/sdlc/SKILL.md`, `.claude/agents/qc-auditor.md`는 **존재하지 않음** |
| 브랜치 보호 | 원격(remote) 미설정 → 조회 불가(미확인) |
| 외부 배포 연결 | 없음 |

## 2. 기존 Claude 설정과의 충돌·재사용

| 대상 | 관찰 | 결정 |
|---|---|---|
| `~/.claude/skills/sdlc*` | 없음 | `sdlc`, `sdlc-*` 이름 사용 가능 |
| `~/.claude/agents/` | `planning-qc-architect`, `acceptance-verifier`, `task-planner` 등 존재. `planner`, `builder`, `qc-verifier` 동명 파일은 없으나 일반명이라 향후 충돌 가능 | 에이전트 이름에 `sdlc-` 접두사 (`sdlc-planner` …) |
| `~/.claude/settings.json` hooks | PreToolUse 등 다수 훅 운영 중 | 전역 설정은 **수정하지 않음**. 경로 가드 훅은 예시만 문서화 |
| Spec Kit / OpenSpec | 설치 흔적 없음 | 신규 |
| `planning-loop-supervisor`, `stargate`, `harness` | 웹 앱 기획→QC 시트(`docs/planning/qc/test-sheet.md`) 중심. 승인 원본 검증·SHA 증거·BUG 재시도 예산은 없음 | 재사용하지 않고 독립 구현. 개념(독립 verifier, 100% 통과 전 완료 금지)만 일치시킴 |

## 3. 재사용 자산

- `templates/*.md` 10종 → CLI 렌더링 원본(수정하지 않음, frontmatter 없는 템플릿은 렌더링 시 헤더 주입)
- `examples/event-registration/*.md` → 데모 기준선 초안
- `docs/03` §5.3/§5.4 JSON → `schemas/`, §7 의사코드 → `scripts/validators/gate.py`

## 4. 변경 대상 (모두 신규 파일)

`SKILL.md`, `skills/`, `agents/`, `install.sh`, `scripts/`, `schemas/`, `tests/`, `evals/`, `examples/event-registration/app/`, `.github/workflows/sdlc-validate.yml`, `docs/{installation,operator-guide,implementation-decisions,security-limitations,demo-walkthrough,branch-protection}.md`.
기존 파일 수정: `README.md`에 구현 현황 섹션 추가만.

## 5. MVP 위험

1. **승인 진위**: 오프라인에서는 외부 승인을 검증할 수 없음 → fail-closed. 로컬 진행용 `local_attested` 승인은 TTY 확인만 요구하므로 에이전트가 의사 TTY로 우회할 수 있다(E1 등급, high-risk·release 불인정).
2. **역할 격리**: 같은 사용자 권한으로 돌아가는 에이전트는 파일을 모두 쓸 수 있다. 실제 격리는 CI·브랜치 보호·별도 작업공간이 담당해야 한다.
3. **훅 우회**: 프로젝트 수준 훅은 셸 명령으로 우회 가능 → 유일한 경계로 쓰지 않음.
