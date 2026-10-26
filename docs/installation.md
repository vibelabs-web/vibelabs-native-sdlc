# 설치

## 요구 사항

- Python 3.10+ (표준 라이브러리만 사용 — `pip install` 불필요), git 2.x
- Claude Code (스킬·에이전트 사용 시)

## 1. 플러그인으로 설치 (권장 · 다른 사람도 동일)

Claude Code 세션에서:

```
/plugin marketplace add vibelabs-web/vibelabs-native-sdlc
/plugin install vibelabs-sdlc@vibelabs-sdlc
```

셸에서는 `claude plugin marketplace add vibelabs-web/vibelabs-native-sdlc` → `claude plugin install vibelabs-sdlc@vibelabs-sdlc` (`--scope project` 로 프로젝트에만).
업데이트: `/plugin marketplace update vibelabs-sdlc`. 사용자에게 업데이트는 `.claude-plugin/plugin.json` 의 version 이 올라갈 때만 간다 — 배포 파일(skills·agents·scripts·schemas·templates·hooks·.claude-plugin)을 바꾼 PR 은 CI(`scripts/ci/check_plugin_version.py`)가 version 상승을 요구한다. 설치 후 진입은 `/vibelabs-sdlc:sdlc`, 에이전트 이름은 `vibelabs-sdlc:sdlc-builder` 처럼 접두사가 붙는다.

- 지원: Claude Code CLI·데스크톱·IDE. **claude.ai/code 클라우드 세션은 로컬에서 설치한 플러그인을 로드하지 않는다**(조직 managed settings 배포만 예외). claude.ai 채팅에 zip 업로드는 스킬만 로드하고 에이전트를 무시하며 git·python 실행 환경이 없어 **미지원**.

## 1-0. npx 한 줄 설치

```bash
npx github:vibelabs-web/vibelabs-native-sdlc            # 플러그인 설치·업데이트 (user 범위)
npx github:vibelabs-web/vibelabs-native-sdlc --scope project
npx github:vibelabs-web/vibelabs-native-sdlc --copy     # 플러그인 대신 ~/.claude/vibelabs-sdlc 복사 + 심링크
npx github:vibelabs-web/vibelabs-native-sdlc --check    # 상태만
npx github:vibelabs-web/vibelabs-native-sdlc --remove   # 이 설치기가 만든 것만 제거
```

- npm 에 `vibelabs-sdlc` 로 등록돼 있어 `npx vibelabs-sdlc [옵션]` 도 같다 (등록본은 npm 에 배포한 버전, `github:` 은 main 최신).
- `bin/vibelabs-sdlc.js`(Node 18+, 외부 의존성 없음)를 실행한다.
- `claude` 명령이 있으면 §1 의 플러그인 명령을 대신 실행하고(이미 있으면 update), 없으면 복사 설치로 넘어간다.
- 복사 설치는 기존 스킬·에이전트나 이 설치기가 만들지 않은 `~/.claude/vibelabs-sdlc` 를 **덮어쓰지 않고 중단**한다. 복사 설치의 진입은 접두사 없는 `/sdlc`.
- `package.json` 과 `plugin.json` 의 version 은 CI 가 같게 유지시킨다.

## 1-1. 개발용: 레포 심링크 (이 레포를 고치는 사람)

```bash
cd /path/to/vibelabs-native-sdlc
./install.sh --check     # 현재 상태 (변경 없음)
./install.sh             # ~/.claude/skills/sdlc* 와 ~/.claude/agents/sdlc-*.md 심링크
./install.sh --remove    # 이 레포를 가리키는 심링크만 제거
```

- 기존 파일이나 다른 곳을 가리키는 심링크가 있으면 **덮어쓰지 않고 건너뛴다**(exit 1).
- 설치 위치 변경: `CLAUDE_SKILLS_DIR`, `CLAUDE_AGENTS_DIR`. 플러그인과 동시에 쓰면 같은 스킬이 두 벌 보이므로 하나만 쓴다.
- `~/.claude/settings.json` 은 수정하지 않는다.

## 2. CLI

스킬은 `${CLAUDE_SKILL_DIR}/../..` (스킬 폴더 기준 하네스 루트)로 CLI 를 찾는다. 다른 위치의 하네스를 쓰려면 `SDLC_HOME`.

```bash
python3 <하네스 루트>/scripts/sdlc.py --help
sdlc() { python3 "${SDLC_HOME:-<하네스 루트>}/scripts/sdlc.py" "$@"; }
```

`<하네스 루트>` = 이 레포 경로, 또는 플러그인 캐시(`~/.claude/plugins/cache/…/vibelabs-sdlc/<버전>`).
대상 프로젝트 루트(또는 그 하위)에서 실행하면 `.sdlc/` 또는 `.git` 을 찾아 루트를 정한다. 다른 위치에서는 `--root`.

## 3. 승인 키

첫 `sdlc approve` 때 `~/.config/vibelabs-sdlc/approval.key`(0600)가 생성된다. `SDLC_APPROVAL_KEY_FILE` 로 위치를 바꿀 수 있지만 **프로젝트 안은 거부**한다. 키를 지우면 그 키로 서명된 로컬 승인은 모두 무효(재승인 필요).

## 4. 가드 훅 (선택 · 소프트 제약)

대상 프로젝트의 `.claude/settings.json` 에 직접 추가한다 (이 하네스는 자동으로 넣지 않는다):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
        "hooks": [
          {"type": "command", "command": "python3 <하네스 루트>/scripts/hooks/guard_paths.py"}
        ]
      }
    ]
  }
}
```

훅은 우회 가능하다 — `docs/security-limitations.md`.

## 5. CI

`.github/workflows/sdlc-validate.yml` 은 이 레포(하네스 자체)용 예시다. 대상 프로젝트에서 쓰려면 하네스를 서브모듈·벤더 디렉터리로 두고
`python <harness>/scripts/sdlc.py ci` 를 필수 체크로 실행한다. 브랜치 보호 권장 설정은 `docs/branch-protection.md`.

## 6. 설치 확인

```bash
python3 -m unittest discover -s tests      # 하네스 자체 테스트
python3 scripts/sdlc.py eval               # EVAL-001~016 (자동 12 / 수동 4)
```

## 부록. npm 배포 절차 (관리자)

1. 배포 파일을 바꾼 PR 은 `package.json`·`plugin.json` version 을 같이 올린다 (CI 강제). main 머지 후 main 에서 배포한다.
2. 계정은 2FA(auth-and-writes)라 `npm publish --otp=<6자리>`.
3. 2FA 우회 토큰으로 배포하면 npm 이 스테이징 배포로 처리해 `0.0.0-stage` 자리표시 버전이 생긴다(2026-10-26 첫 배포 때 생김 — 무해, `latest` 는 실제 버전). 토큰을 썼다면 배포 직후 폐기한다.
