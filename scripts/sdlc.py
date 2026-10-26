#!/usr/bin/env python3
"""VibeLabs SDLC Harness CLI — 변경 단위 산출물·게이트·QC 증거를 결정적으로 관리한다.

종료 코드: 0 성공/ALLOW · 1 검증 실패/BLOCK · 2 사용 오류 · 3 MANUAL_VERIFICATION_REQUIRED
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import bugs, changes, gitutil, lifecycle, release, report, risk, runner  # noqa: E402
from core import state as sm  # noqa: E402
from core.util import SdlcError  # noqa: E402
from validators import approvals, check, drift, gate as g  # noqa: E402

SKILL_FOR_STAGE = {
    "INTAKE": "sdlc-intent", "INTENT_DRAFT": "sdlc-intent",
    "INTENT_APPROVED": "sdlc-spec", "SPEC_DRAFT": "sdlc-spec",
    "SPEC_APPROVED": "sdlc-plan + sdlc-qc-design (병렬·독립)", "PLAN_TEST_DRAFT": "sdlc-plan + sdlc-qc-design (병렬·독립)",
    "BASELINE_APPROVED": "sdlc-build", "BUILDING": "sdlc-build", "DEFECT_OPEN": "sdlc-build",
    "QC_RUNNING": "sdlc-qc-run",
    "QC_PASSED": "sdlc-release", "REVIEW_PENDING": "sdlc-release", "RELEASE_APPROVED": "sdlc-release",
    "MONITORING": "sdlc-maintain",
}
EXIT_FOR = {g.ALLOW: 0, g.BLOCK: 1, g.MANUAL: 3}


def out(args, data, text: str) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(text)


def project(args) -> changes.Project:
    return changes.Project(Path(args.root)) if args.root else changes.Project.discover()


def require_tty(what: str) -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise SdlcError(f"{what} 은 사람이 직접 터미널(TTY)에서 실행해야 합니다 — 에이전트·파이프 실행 거부")


def confirm(prompt: str, expected: str) -> None:
    ans = input(f"{prompt}\n확인하려면 '{expected}' 를 입력: ").strip()
    if ans != expected:
        raise SdlcError("확인 문구 불일치 — 취소")


# ---------------------------------------------------------------- commands

def cmd_new(args):
    p = project(args)
    level, hits, warning = risk.resolve(args.risk, f"{args.title} {args.description or ''}")
    ch = p.create(args.title, level, hits, args.source)
    msg = [f"생성: {ch.id} ({level})", f"  {ch.path('intent')}"]
    if warning:
        msg.append(f"  경고: {warning}")
    if level == "high":
        msg.append("  high-risk: 모든 승인은 외부 신뢰 승인(E2+) 필요 — 로컬 승인으로 통과 불가")
    out(args, {"change_id": ch.id, "risk_level": level, "risk_hits": hits, "warning": warning}, "\n".join(msg))
    return 0


def cmd_list(args):
    p = project(args)
    rows = [{"change_id": c, "stage": p.load(c).state["stage"], "title": p.load(c).state.get("title")}
            for c in p.change_ids()]
    out(args, rows, "\n".join(f"{r['change_id']}  {r['stage']:<18} {r['title']}" for r in rows) or "변경 없음")
    return 0


def cmd_inspect(args):
    ch = project(args).load(args.change_id)
    st = ch.state
    rep = check.validate(ch)
    nexts = []
    for t in sm.allowed_next(st["stage"]):
        r = g.gate(ch, t)
        nexts.append(r.to_dict())
    open_bugs = [{"id": b.id, "status": b.status, "fix_attempts": b.meta.get("fix_attempts")}
                 for b in bugs.load_all(ch) if not b.resolved]
    data = {"change_id": ch.id, "title": st.get("title"), "stage": st["stage"], "risk_level": st["risk_level"],
            "skill": SKILL_FOR_STAGE.get(st["stage"]), "validate": rep.to_dict(), "next": nexts,
            "open_bugs": open_bugs, "blocked_reasons": st.get("blocked_reasons", []),
            "approvals": {k: approvals.verify(ch.project.root, ch.id, v).__dict__
                          for k, v in st.get("approvals", {}).items()}}
    lines = [f"{ch.id}  {st.get('title')}", f"  stage: {st['stage']} · risk: {st['risk_level']} · "
             f"다음 스킬: {data['skill']}",
             f"  validate: errors {len(rep.errors)} · blockers {len(rep.blockers)}"]
    if rep.stale:
        lines.append(f"  stale: {rep.stale}")
    for k, v in data["approvals"].items():
        lines.append(f"  승인 {k}: {v['status']} {v['level']} — {v['reason']}")
    for n in nexts:
        lines.append(f"  → {n['to']}: {n['decision']}")
        for i in n["reasons"][:8]:
            lines.append(f"      - [{i['severity']}] {i['code']}: {i['message']}")
        for m in n["manual_verification"]:
            lines.append(f"      - [manual] {m}")
    for b in open_bugs:
        lines.append(f"  BUG {b['id']}: {b['status']} (시도 {b['fix_attempts']})")
    out(args, data, "\n".join(lines))
    return 0


def cmd_draft(args):
    ch = project(args).load(args.change_id)
    path = changes.render_template(ch, args.artifact)
    print(f"작성: {path}")
    return 0


def cmd_validate(args):
    p = project(args)
    ids = p.change_ids() if args.all else [args.change_id]
    if not ids or ids == [None]:
        raise SdlcError("change_id 또는 --all 필요")
    reports = [check.validate(p.load(c)) for c in ids]
    failed = any(r.errors or (args.strict and r.blockers) for r in reports)
    text = []
    for r in reports:
        text.append(f"{r.change_id} [{r.stage}] errors={len(r.errors)} blockers={len(r.blockers)}"
                    + (f" trace_coverage={r.index['trace_coverage']}" if r.index else ""))
        text += [f"  {i}" for i in r.issues]
    out(args, {"ok": not failed, "changes": [r.to_dict() for r in reports]}, "\n".join(text) or "변경 없음")
    return 1 if failed else 0


def cmd_approve(args):
    ch = project(args).load(args.change_id)
    scope = args.scope
    if scope not in sm.APPROVAL_SCOPES:
        raise SdlcError(f"scope 는 {list(sm.APPROVAL_SCOPES)}")
    require_tty("승인")
    root = ch.project.root
    if scope == "release":
        bound = {"commit": gitutil.head(root), "qc_run": ch.state.get("last_verification_run")}
    else:
        bound = g.current_bound(ch, scope)
    missing = [a for a, s in bound.items() if s is None]
    if missing:
        raise SdlcError(f"승인 대상 파일 없음: {missing}")
    approver = gitutil.user_name(root) or os.environ.get("USER", "unknown")
    print(f"[{ch.id}] {scope} 승인 — 위험도 {ch.state['risk_level']}, 승인자 {approver}")
    for a, s in bound.items():
        print(f"  {a}: {s}")
    if ch.state["risk_level"] == "high" or scope == "release":
        print("  주의: 이 로컬 승인은 E1 — high-risk/release 게이트는 외부 승인 없이는 통과하지 않음")
    confirm("내용을 직접 검토했습니까?", ch.id)
    rec = approvals.make_local_record(root, ch.id, scope, bound, approver)
    ch.state.setdefault("approvals", {})[scope] = rec
    ch.record("approval", scope=scope, kind=rec["kind"], ref=rec["ref"], approver=approver)
    ch.save()
    print(f"기록: {rec['ref']} (local_attested, E1)")
    return 0


def cmd_gate(args):
    ch = project(args).load(args.change_id)
    res = g.gate(ch, args.stage)
    if res.decision == g.ALLOW and not args.dry_run:
        g.apply(ch, res)
    elif res.decision != g.ALLOW and not args.dry_run:
        g.record_refusal(ch, res)
    lines = [f"{ch.id}: {res.current} → {res.target} = {res.decision}" + (" (dry-run)" if args.dry_run else "")]
    lines += [f"  {i}" for i in res.reasons]
    lines += [f"  [MANUAL] {m}" for m in res.manual]
    out(args, res.to_dict(), "\n".join(lines))
    return EXIT_FOR[res.decision]


def cmd_reopen(args):
    ch = project(args).load(args.change_id)
    r = lifecycle.reopen(ch, args.to, args.reason)
    print(f"{ch.id}: {r['from']} → {r['to']} (승인 무효화: {r['cleared_approvals'] or '없음'}) — 이전 증거는 stale")
    return 0


def cmd_build_check(args):
    ch = project(args).load(args.change_id)
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    rec = lifecycle.build_check(ch, cmd)
    out(args, rec, f"build check exit={rec['exit_code']} commit={rec['commit_sha']} dirty={rec['dirty']} "
                   f"log={rec['log_path']}")
    return 0 if rec["exit_code"] == 0 else 1


def cmd_qc_run(args):
    ch = project(args).load(args.change_id)
    r = runner.run(ch, isolated=args.isolated, allow_dirty=args.allow_dirty)
    run = r["run"]
    lines = [f"{run['run_id']} @ {run['commit_sha'][:12]} ({run['environment']})"]
    lines += [f"  {c['tc_id']}: {c['result']}  {c['summary']}" for c in run["cases"]]
    lines += [f"  · {e}" for e in r["bug_events"]]
    fails = [c for c in run["cases"] if c["result"] != "PASS"]
    lines.append("다음: " + (f"`sdlc gate {ch.id} DEFECT_OPEN`" if bugs_open(ch) else f"`sdlc gate {ch.id} QC_PASSED`"))
    out(args, r, "\n".join(lines))
    return 1 if fails else 0


def bugs_open(ch) -> bool:
    return any(not b.resolved for b in bugs.load_all(ch))


def cmd_bug(args):
    ch = project(args).load(args.change_id)
    if args.bug_cmd == "list":
        rows = [{"id": b.id, **b.meta} for b in bugs.load_all(ch)]
        out(args, rows, "\n".join(f"{r['id']}  {r.get('status'):<16} {r.get('severity'):<8} "
                                  f"TC={r.get('test_ids')} 시도={r.get('fix_attempts')}" for r in rows) or "BUG 없음")
        return 0
    if args.bug_cmd == "new":
        b = bugs.create(ch, req_ids=args.req or [], tc_ids=args.tc or [], title=args.title, severity=args.severity,
                        expected=args.expected, actual=args.actual, repro=args.repro or [],
                        commit_sha=gitutil.head(ch.project.root), run_id=ch.state.get("last_verification_run"),
                        log_ref=None)
        ch.save()
        print(f"생성: {b.path}")
        return 0
    b = bugs.get(ch, args.bug_id)
    if args.bug_cmd == "transition":
        human = False
        if b.status in sm.HUMAN_ONLY_BUG_FROM:
            require_tty(f"{b.id} {b.status} 해제")
            confirm(f"{b.id} 를 {b.status} 에서 {args.to} 로 — 결정 내용을 --note 로 남겼습니까?", b.id)
            human = True
        bugs.transition(ch, b, args.to, role=args.role, ref=args.note or "", human=human)
        ch.save()
        print(f"{b.id}: → {args.to}")
        return 0
    if args.bug_cmd == "classify":
        b.meta["classification"] = args.kind
        b.add_history(args.role, f"분류 → {args.kind}", args.note or "-")
        b.save()
        if args.kind in ("flaky", "infra", "oracle") and b.status not in ("escalated", "closed"):
            bugs.transition(ch, b, "blocked_spec" if args.kind == "oracle" else "escalated",
                            role=args.role, ref=f"{args.kind}: 사람 판단 필요")
        ch.save()
        print(f"{b.id}: classification={args.kind} status={b.status}")
        return 0
    return 2


def cmd_report(args):
    ch = project(args).load(args.change_id)
    data = report.build(ch)
    written = [] if args.no_write else report.write_markdown(ch, data)
    lines = [f"{ch.id} trace_coverage={data['trace_coverage']} verified_coverage={data['verified_coverage']} "
             f"run={data['run_id']} valid={data['run_valid']}"]
    lines += [f"  {r['req']}: {r['verdict']} tasks={r['tasks']} tcs={r['tcs']} bugs={r['bugs']}" for r in data["rows"]]
    lines += [f"  증거 무효: {i}" for i in data["run_issues"]]
    if written:
        lines.append(f"  작성: {', '.join(written)}")
    out(args, data, "\n".join(lines))
    return 0


def cmd_release(args):
    ch = project(args).load(args.change_id)
    r = release.draft(ch)
    text = f"작성: {', '.join(r['written'])} — 배포 명령은 실행하지 않음"
    if r["release_gate"]:
        text += f"\nRELEASE_APPROVED 사전 점검: {r['release_gate']['decision']}"
        text += "".join(f"\n  [MANUAL] {m}" for m in r["release_gate"]["manual_verification"])
    out(args, r, text)
    return 0


def cmd_deploy(args):
    print("배포는 이 하네스의 범위 밖입니다 (MVP: 자동 프로덕션 배포 미구현·금지).\n"
          "승인 경로: QC_PASSED → REVIEW_PENDING → 외부 승인 시스템(PR 리뷰·보호 브랜치·CI 배포 권한)에서 "
          "지정된 운영 책임자가 승인·실행.", file=sys.stderr)
    return 1


def cmd_drift(args):
    ch = project(args).load(args.change_id)
    rep = check.validate(ch)
    issues, out_of_plan = drift.check(ch, rep.parsed.get("plan"))
    out(args, {"out_of_plan": out_of_plan, "issues": [i.to_dict() for i in issues]},
        "\n".join(str(i) for i in issues) or "계획 밖 변경 없음")
    return 1 if any(i.severity != "warning" for i in issues) else 0


def cmd_demo_init(args):
    from core import demo
    p = project(args)
    ch = demo.init(p, change_id=args.change_id)
    print(f"데모 변경 {ch.id} 생성 — app/ 과 {ch.dir.relative_to(p.root)} 를 확인하세요 "
          f"(docs/demo-walkthrough.md)")
    return 0


def cmd_eval(args):
    from core import evals
    results = evals.run_all(only=args.case)
    lines = [f"{r['id']}  {r['status']:<8} {r['title']}" + (f"  — {r['detail']}" if r.get("detail") else "")
             for r in results]
    auto = [r for r in results if r["mode"] == "auto"]
    passed = sum(r["status"] == "PASS" for r in auto)
    lines.append(f"자동 {passed}/{len(auto)} PASS · 수동(미검증) {len(results) - len(auto)}")
    out(args, results, "\n".join(lines))
    return 0 if passed == len(auto) else 1


def cmd_ci(args):
    args.all, args.strict, args.change_id = True, False, None
    return cmd_validate(args)


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sdlc", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="대상 프로젝트 루트 (기본: 현재 위치에서 .sdlc/.git 탐색)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, json_=True):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        if json_:
            sp.add_argument("--json", action="store_true", help="JSON 출력")
        return sp

    sp = add("new", cmd_new, "변경 생성 (CHG-YYYYMMDD-NNN) + intent.md")
    sp.add_argument("--title", required=True)
    sp.add_argument("--description", default="")
    sp.add_argument("--risk", default="auto", choices=["auto", *risk.LEVELS])
    sp.add_argument("--source", help="출처 (대화/이슈/인시던트 링크)")
    add("list", cmd_list, "변경 목록")
    sp = add("inspect", cmd_inspect, "현재 단계·차단 사유·다음 허용 단계")
    sp.add_argument("change_id")
    sp = add("draft", cmd_draft, "템플릿에서 산출물 초안 생성 (덮어쓰지 않음)", json_=False)
    sp.add_argument("change_id")
    sp.add_argument("artifact", choices=sorted(changes.TEMPLATE_FOR))
    sp = add("validate", cmd_validate, "스키마·ID·추적성·기준선·오라클 잠금 검사")
    sp.add_argument("change_id", nargs="?")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--strict", action="store_true", help="blocker 도 실패로 처리")
    sp = add("approve", cmd_approve, "로컬 TTY 승인 기록 (E1 — high-risk/release 불인정)", json_=False)
    sp.add_argument("change_id")
    sp.add_argument("scope", choices=list(sm.APPROVAL_SCOPES))
    sp = add("gate", cmd_gate, "단계 전이 판정 (ALLOW 시 적용)")
    sp.add_argument("change_id")
    sp.add_argument("stage", choices=sm.STAGES)
    sp.add_argument("--dry-run", action="store_true")
    sp = add("reopen", cmd_reopen, "초안 단계로 되돌리고 승인·기준선·증거 무효화", json_=False)
    sp.add_argument("change_id")
    sp.add_argument("--to", required=True, choices=sm.REOPEN_TARGETS)
    sp.add_argument("--reason", required=True)

    sp = sub.add_parser("build", help="Builder 자체 검사")
    bsub = sp.add_subparsers(dest="build_cmd", required=True)
    bc = bsub.add_parser("check", help="sdlc build check <id> -- <cmd...>")
    bc.set_defaults(fn=cmd_build_check)
    bc.add_argument("--json", action="store_true")
    bc.add_argument("change_id")
    bc.add_argument("cmd", nargs=argparse.REMAINDER)

    sp = sub.add_parser("qc", help="QC 실행")
    qsub = sp.add_subparsers(dest="qc_cmd", required=True)
    qr = qsub.add_parser("run", help="고정 SHA 에서 qc-manifest 실행 → RUN 증거 + BUG")
    qr.set_defaults(fn=cmd_qc_run)
    qr.add_argument("--json", action="store_true")
    qr.add_argument("change_id")
    qr.add_argument("--isolated", action="store_true", help="임시 git worktree 에서 실행")
    qr.add_argument("--allow-dirty", action="store_true", help="미커밋 상태 실행 (증거는 게이트 무효)")

    sp = sub.add_parser("bug", help="결함 티켓")
    bsub = sp.add_subparsers(dest="bug_cmd", required=True)
    for name in ("list", "new", "transition", "classify"):
        b = bsub.add_parser(name)
        b.set_defaults(fn=cmd_bug)
        b.add_argument("--json", action="store_true")
        b.add_argument("change_id")
        if name in ("transition", "classify"):
            b.add_argument("bug_id")
            b.add_argument("--role", required=True, choices=["builder", "qc-verifier", "qc-architect", "human"])
            b.add_argument("--note")
        if name == "transition":
            b.add_argument("--to", required=True, choices=list(sm.BUG_TRANSITIONS))
        if name == "classify":
            b.add_argument("kind", choices=["defect", "flaky", "infra", "oracle"])
        if name == "new":
            b.add_argument("--tc", action="append")
            b.add_argument("--req", action="append")
            b.add_argument("--title", required=True)
            b.add_argument("--severity", default="high", choices=["critical", "high", "medium", "low"])
            b.add_argument("--expected", required=True)
            b.add_argument("--actual", required=True)
            b.add_argument("--repro", action="append")

    sp = add("report", cmd_report, "추적성 매트릭스·QC 보고서 생성")
    sp.add_argument("change_id")
    sp.add_argument("--no-write", action="store_true")
    sp = add("release", cmd_release, "review.md/release.md 체크리스트 초안 (명령 실행 없음)")
    sp.add_argument("change_id")
    sp = add("deploy", cmd_deploy, "(미구현·금지) 배포 승인 경로 안내만", json_=False)
    sp.add_argument("change_id", nargs="?")
    sp = add("drift", cmd_drift, "plan.md 대비 계획 밖 변경 검사")
    sp.add_argument("change_id")
    sp = add("demo-init", cmd_demo_init, "행사 신청 데모 변경 생성", json_=False)
    sp.add_argument("--change-id", help="예: CHG-DEMO-001")
    sp = add("eval", cmd_eval, "하네스 자체 평가 (evals/cases)")
    sp.add_argument("--case", action="append")
    add("ci", cmd_ci, "CI 진입점: 모든 변경 validate")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except SdlcError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
