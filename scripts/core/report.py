"""추적성 매트릭스·QC 보고서 생성 (`sdlc report`). 숫자의 원본은 RUN 증거이며, Markdown 은 보기용이다."""
from __future__ import annotations

from core import bugs, gitutil
from core.util import atomic_write_text, now_iso
from validators import check, evidence, frontmatter


def build(change) -> dict:
    rep = check.validate(change)
    head = gitutil.head(change.project.root)
    run_id = change.state.get("last_verification_run")
    run = evidence.load_run(change, run_id) if run_id else None
    run_issues = evidence.verify(change, run, head) if run else []
    run_valid = run is not None and not run_issues
    results = {c["tc_id"]: c["result"] for c in (run or {}).get("cases", [])}
    all_bugs = bugs.load_all(change)
    idx = rep.index or {"reqs": {}, "tasks": {}, "tcs": {}}
    rows = []
    must_total = must_verified = 0
    for rid, v in idx["reqs"].items():
        tc_res = {tc: (results.get(tc, "NOT_RUN") if run_valid else ("STALE" if run else "NOT_RUN"))
                  for tc in v["tcs"]}
        rbugs = [b.id for b in all_bugs if rid in (b.meta.get("requirement_ids") or []) and not b.resolved]
        if v["open"]:
            verdict = "OPEN"
        elif not v["tcs"] or not v["tasks"]:
            verdict = "UNTRACED"
        elif all(r == "PASS" for r in tc_res.values()) and not rbugs:
            verdict = "PASS"
        elif any(r == "FAIL" for r in tc_res.values()):
            verdict = "FAIL"
        else:
            verdict = "NOT_VERIFIED"
        if v["must"]:
            must_total += 1
            must_verified += verdict == "PASS"
        rows.append({"req": rid, "priority": v["priority"], "must": v["must"], "tasks": v["tasks"],
                     "tcs": tc_res, "bugs": rbugs, "verdict": verdict})
    return {
        "change_id": change.id, "stage": change.state["stage"], "generated_at": now_iso(),
        "head": head, "run_id": run_id, "run_valid": run_valid,
        "run_issues": [str(i) for i in run_issues], "rows": rows,
        "trace_coverage": idx.get("trace_coverage"),
        "verified_coverage": (must_verified / must_total) if must_total else None,
        "must_total": must_total, "must_verified": must_verified,
        "baselines": change.state.get("baselines", {}),
        "bugs": [{"id": b.id, "status": b.status, "severity": b.meta.get("severity"),
                  "fix_attempts": b.meta.get("fix_attempts")} for b in all_bugs],
        "validate_errors": len(rep.errors), "validate_blockers": len(rep.blockers),
    }


def _pct(x):
    return "N/A" if x is None else f"{x * 100:.0f}%"


def write_markdown(change, data: dict) -> list[str]:
    b = data["baselines"]
    meta = {"change_id": change.id, "revision": "0.1.0", "status": "draft", "author_role": "sdlc-cli",
            "source_refs": [data["run_id"]] if data["run_id"] else [], "approval_ref": None}
    lines = [
        "# Requirements Traceability Matrix (자동 생성 — 손으로 고치지 말 것)", "",
        f"- 생성: {data['generated_at']} · stage: `{data['stage']}` · HEAD: `{data['head'] or '미확인'}`",
        f"- spec SHA: `{b.get('spec', '미기준선')}` · plan SHA: `{b.get('plan', '미기준선')}` · "
        f"test-spec SHA: `{b.get('test_spec', '미기준선')}`",
        f"- 증거: {data['run_id'] or '없음'} ({'유효' if data['run_valid'] else '무효/없음'})",
        f"- trace_coverage: {_pct(data['trace_coverage'])} · verified_coverage: {_pct(data['verified_coverage'])} "
        f"({data['must_verified']}/{data['must_total']} 필수 REQ) — 테스트 통과 개수 ≠ 요구사항 완성률", "",
        "| REQ-ID | 우선순위 | TASK-ID | TC-ID (결과) | RUN-ID | BUG-ID | 판정 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in data["rows"]:
        tcs = ", ".join(f"{k} ({v})" for k, v in r["tcs"].items()) or "-"
        lines.append(f"| {r['req']} | {r['priority']} | {', '.join(r['tasks']) or '-'} | {tcs} | "
                     f"{data['run_id'] or '-'} | {', '.join(r['bugs']) or '-'} | {r['verdict']} |")
    if data["run_issues"]:
        lines += ["", "## 증거 무효 사유", *[f"- {i}" for i in data["run_issues"]]]
    atomic_write_text(change.path("traceability"), frontmatter.dump(meta) + "\n" + "\n".join(lines) + "\n")

    verdict = "PASS" if (data["run_valid"] and data["must_total"] and data["must_verified"] == data["must_total"]
                         and not any(x["status"] not in ("verified_fixed", "closed") for x in data["bugs"])) else "FAIL"
    if not data["run_id"]:
        verdict = "MANUAL_REVIEW_REQUIRED"
    q = [
        f"# QC Report — {change.id} (자동 생성)", "",
        "## Baselines",
        f"- Intent / Spec / Plan / Test Spec SHA: {b.get('intent', '-')} / {b.get('spec', '-')} / "
        f"{b.get('plan', '-')} / {b.get('test_spec', '-')}",
        f"- Actual implementation SHA: {data['head'] or '미확인'}",
        f"- QC Agent / Environment: qc-verifier / {data['run_id'] or '미실행'}", "",
        "## Coverage", "| REQ-ID | TC-ID | 결과(PASS/FAIL/BLOCKED/NOT_RUN) | 증거 | 관련 BUG |", "|---|---|---|---|---|",
    ]
    for r in data["rows"]:
        for tc, res in (r["tcs"] or {"-": "NOT_RUN"}).items():
            q.append(f"| {r['req']} | {tc} | {res} | {data['run_id'] or '-'} | {', '.join(r['bugs']) or '-'} |")
    q += ["", "## Deviations",
          *([f"- {i}" for i in data["run_issues"]] or ["- 증거 무효 사유 없음"]), "",
          "## Verdict", f"- {verdict}",
          f"- 차단 결함: {', '.join(x['id'] for x in data['bugs'] if x['status'] not in ('verified_fixed', 'closed')) or '없음'}",
          "- 담당 승인/최종 결과: 미확인 (이 보고서는 승인이 아님)"]
    meta_q = {**meta, "author_role": "qc-verifier"}
    atomic_write_text(change.path("qc_report"), frontmatter.dump(meta_q) + "\n" + "\n".join(q) + "\n")
    return [change.path("traceability").name, change.path("qc_report").name]
