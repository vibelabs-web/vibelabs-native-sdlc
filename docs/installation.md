# 설치

## 요구 사항

- Python 3.10+ (표준 라이브러리만 사용 — `pip install` 불필요), git 2.x
- Claude Code (스킬·에이전트 사용 시)

## 1. 스킬·에이전트 등록

```bash
cd /path/to/vibelabs-native-sdlc
./install.sh --check     # 현재 상태 (변경 없음)
./install.sh             # ~/.claude/skills/sdlc, sdlc-* 와 ~/.claude/agents/sdlc-*.md 심링크
./install.sh --remove    # 이 레포를 가리키는 심링크만 제거
```

- 기존 파일이나 다른 곳을 가리키는 심링크가 있으면 **덮어쓰지 않고 건너뛴다**(exit 1).
- 설치 위치 변경: `CLAUDE_SKILLS_DIR`, `CLAUDE_AGENTS_DIR`.
- `~/.claude/settings.json` 은 수정하지 않는다.

## 2. CLI

```bash
python3 ~/.claude/skills/sdlc/scripts/sdlc.py --help
# 편의 함수
sdlc() { python3 "${SDLC_HOME:-$HOME/.claude/skills/sdlc}/scripts/sdlc.py" "$@"; }
```

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
          {"type": "command", "command": "python3 ~/.claude/skills/sdlc/scripts/hooks/guard_paths.py"}
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
