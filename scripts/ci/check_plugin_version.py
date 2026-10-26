#!/usr/bin/env python3
"""CI: 플러그인 사용자에게 가는 파일을 바꾼 PR 은 `.claude-plugin/plugin.json` 의 version 을 올려야 한다.
npx 설치기용 `package.json` 이 있으면 그 version 도 같아야 한다.

플러그인은 version 이 바뀌어야 사용자에게 업데이트된다. 스킬·에이전트·CLI 를 고치고 version 을 그대로 두면
머지돼도 설치한 사람에게는 옛 버전이 계속 돈다.

입력 환경변수: BASE_REF
"""
import json
import os
import re
import subprocess
import sys

MANIFEST = ".claude-plugin/plugin.json"
PACKAGE = "package.json"
SHIPPED = ["skills/", "agents/", "scripts/", "schemas/", "templates/", "hooks/", ".claude-plugin/", "bin/", PACKAGE]
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True)


def version(text):
    v = json.loads(text).get("version", "")
    m = SEMVER.match(v)
    return v, (tuple(int(x) for x in m.groups()) if m else None)


def main() -> int:
    base = os.environ.get("BASE_REF", "").strip()
    if not base:
        print("::error::BASE_REF 가 비어 있음 — 워크플로가 github.event.pull_request.base.ref 를 넘겨야 함")
        return 2
    with open(MANIFEST, encoding="utf-8") as f:
        new_v, new_t = version(f.read())
    if new_t is None:
        print(f"::error::{MANIFEST} version '{new_v}' 이 X.Y.Z 형식이 아님")
        return 1
    if os.path.isfile(PACKAGE):
        with open(PACKAGE, encoding="utf-8") as f:
            pkg_v, _ = version(f.read())
        if pkg_v != new_v:
            print(f"::error::{PACKAGE} version {pkg_v} ≠ {MANIFEST} version {new_v} — 둘을 같이 올려야 함")
            return 1
    old = git("show", f"origin/{base}:{MANIFEST}")
    if old.returncode != 0:
        print(f"base({base}) 에 {MANIFEST} 없음 — 첫 배포, 상승 검사 생략")
        return 0
    old_v, old_t = version(old.stdout)
    d = git("diff", "--name-only", f"origin/{base}...HEAD")
    if d.returncode != 0:
        print(f"::error::git diff 실패: {d.stderr.strip()}")
        return 2
    shipped = [p for p in d.stdout.split() if p.startswith(tuple(SHIPPED)) and p != MANIFEST]
    if not shipped:
        print("플러그인 배포 파일 변경 없음")
        return 0
    print("플러그인 배포 파일 변경:", *shipped, sep="\n  ")
    if old_t is not None and new_t <= old_t:
        print(f"::error::version 을 올려야 함 (base {old_v} → PR {new_v}) — 그대로면 설치한 사람에게 업데이트가 가지 않음")
        return 1
    print(f"version {old_v} → {new_v} — 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
