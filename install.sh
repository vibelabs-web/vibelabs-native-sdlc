#!/usr/bin/env bash
# vibelabs-native-sdlc: 로컬 스킬·에이전트를 Claude Code 전역 디렉터리에 심링크 등록
#
# 진입 스킬 1개(sdlc) + 단계 스킬 8개 + 에이전트 7개. 플러그인으로 설치했다면 이 스크립트는 필요 없다. 원본은 이 레포에 있고, 전역에서는 심링크로만 접근한다.
# 기존 파일(심링크가 아닌 것)이나 다른 곳을 가리키는 심링크는 절대 덮어쓰지 않는다.
#
# 사용법:
#   ./install.sh           # 등록
#   ./install.sh --check   # 상태 점검 (변경 없음)
#   ./install.sh --remove  # 이 레포를 가리키는 심링크만 제거
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
AGENTS_DIR="${CLAUDE_AGENTS_DIR:-$HOME/.claude/agents}"
MODE="install"
case "${1:-}" in
  --check) MODE="check" ;;
  --remove) MODE="remove" ;;
  "") ;;
  *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
esac

MAP=()
for d in "$ROOT"/skills/sdlc*/; do
  n="$(basename "$d")"; MAP+=("$SKILLS_DIR/$n:${d%/}")
done
for f in "$ROOT"/agents/sdlc-*.md; do
  MAP+=("$AGENTS_DIR/$(basename "$f"):$f")
done

fail=0
for pair in "${MAP[@]}"; do
  dest="${pair%%:*}"; src="${pair#*:}"
  if [ -L "$dest" ]; then cur="$(readlink "$dest")"; else cur=""; fi
  case "$MODE" in
    check)
      if [ "$cur" = "$src" ]; then echo "OK      $dest"
      elif [ -e "$dest" ] || [ -L "$dest" ]; then echo "CONFLICT $dest (기존 항목 — 이 레포 아님)"; fail=1
      else echo "MISSING $dest"; fail=1; fi ;;
    install)
      if [ "$cur" = "$src" ]; then echo "유지    $dest"
      elif [ -e "$dest" ] || [ -L "$dest" ]; then echo "건너뜀  $dest (기존 항목 보존 — 수동 확인 필요)" >&2; fail=1
      else mkdir -p "$(dirname "$dest")" && ln -s "$src" "$dest" && echo "등록    $dest -> $src"; fi ;;
    remove)
      if [ "$cur" = "$src" ]; then rm "$dest" && echo "제거    $dest"; fi ;;
  esac
done

if [ "$MODE" = "install" ]; then
  echo
  echo "CLI: python3 $ROOT/scripts/sdlc.py --help"
  echo "가드 훅(선택): docs/installation.md 의 PreToolUse 설정 예시 참고 — 이 스크립트는 settings.json 을 수정하지 않는다."
fi
exit $fail
