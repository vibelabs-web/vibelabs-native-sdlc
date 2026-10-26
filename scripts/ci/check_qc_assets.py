#!/usr/bin/env python3
"""CI: PR 이 잠긴 QC 자산(test-spec·qc-manifest·qc-tests)을 바꿨다면 승인 근거를 요구한다.

통과 조건 (하나면 됨)
1. PR 에 `qc-oracle-approved` 라벨 (사람 QA 모드)
2. **base 브랜치** 정책(.sdlc/policies/approvers.json)의 plan_test 명단에 있는 계정(봇 포함)이 이 PR 을 APPROVED 했고,
   그 리뷰 커밋 이후 QC 자산이 바뀌지 않았다 (완전 자율 모드).
PR 안에서 정책을 고쳐 자기 자신을 승인자로 넣는 것을 막으려고 정책은 base 쪽에서 읽는다.

입력 환경변수: BASE_REF, PR_NUMBER, REPO, LABELS(JSON), GH_TOKEN
"""
import json
import os
import subprocess
import sys

PATTERNS = [".sdlc/changes/*/test-spec.md", ".sdlc/changes/*/qc-manifest.json", ".sdlc/changes/*/qc-tests/**"]


def git(*a, check=True):
    p = subprocess.run(["git", *a], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"git {' '.join(a)}: {p.stderr}")
    return p


def gh(path):
    p = subprocess.run(["gh", "api", path, "--paginate"], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"gh api {path}: {p.stderr}")
    return json.loads(p.stdout or "[]")


def main() -> int:
    base = os.environ.get("BASE_REF", "").strip()
    if not base:
        print("::error::BASE_REF 가 비어 있음 — 워크플로가 github.event.pull_request.base.ref 를 넘겨야 함")
        return 2
    changed = git("diff", "--name-only", f"origin/{base}...HEAD", "--", *PATTERNS).stdout.split()
    if not changed:
        print("QC 자산 변경 없음")
        return 0
    print("QC 자산 변경:", *changed, sep="\n  ")
    if "qc-oracle-approved" in json.loads(os.environ.get("LABELS") or "[]"):
        print("qc-oracle-approved 라벨 확인 — 통과")
        return 0
    pol = git("show", f"origin/{base}:.sdlc/policies/approvers.json", check=False)
    if pol.returncode != 0:
        print(f"::error::base({base}) 에 승인 정책이 없음 — 라벨 또는 정책 필요")
        return 1
    allowed = {x.lower() for x in json.loads(pol.stdout).get("scopes", {}).get("plan_test", [])}
    reviews = gh(f"repos/{os.environ['REPO']}/pulls/{os.environ['PR_NUMBER']}/reviews")
    for r in reviews:
        who = (r.get("user") or {}).get("login", "").lower()
        if r.get("state") != "APPROVED" or who not in allowed:
            continue
        commit = r.get("commit_id")
        if git("cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
            git("fetch", "-q", "origin", commit, check=False)
        diff = git("diff", "--name-only", commit, "HEAD", "--", *PATTERNS, check=False)
        if diff.returncode == 0 and not diff.stdout.strip():
            print(f"{who} 의 승인 리뷰({commit[:12]}) 이후 QC 자산 변경 없음 — 통과")
            return 0
        print(f"{who} 승인({commit[:12]}) 이후 바뀐 QC 자산: {diff.stdout.split()}")
    print(f"::error::QC 자산 변경에 대한 승인 근거 없음 (plan_test 명단 {sorted(allowed)} 의 유효한 APPROVED 리뷰 필요)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
