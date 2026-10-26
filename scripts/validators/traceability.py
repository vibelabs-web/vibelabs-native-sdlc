"""REQ ↔ TASK ↔ TC 추적성 검사 (SOP §5, traceability 템플릿의 자동 검사 규칙)."""
from __future__ import annotations

from collections import Counter

from validators.artifacts import Parsed
from validators.issues import Issue, blocker, err


def _dups(rows, kind: str, rel: str) -> list[Issue]:
    c = Counter(r.id for r in rows)
    return [err("DUPLICATE_ID", f"{kind} {i} 가 {n}회 정의됨", rel) for i, n in c.items() if n > 1]


def build_index(spec: Parsed, plan: Parsed | None, test: Parsed | None) -> dict:
    reqs = {r.id: {"priority": r.priority, "status": r.status or "", "must": r.is_must, "open": r.is_open,
                   "source": r.source, "tasks": [], "tcs": []} for r in spec.reqs}
    tasks = {t.id: {"reqs": t.reqs, "files": t.files, "evidence_tcs": t.evidence_tcs} for t in (plan.tasks if plan else [])}
    tcs = {c.id: {"reqs": c.reqs, "priority": c.priority} for c in (test.tcs if test else [])}
    for tid, t in tasks.items():
        for r in t["reqs"]:
            if r in reqs:
                reqs[r]["tasks"].append(tid)
    for cid, c in tcs.items():
        for r in c["reqs"]:
            if r in reqs:
                reqs[r]["tcs"].append(cid)
    must = [r for r, v in reqs.items() if v["must"]]
    traced = [r for r in must if reqs[r]["tasks"] and reqs[r]["tcs"]]
    return {
        "reqs": reqs, "tasks": tasks, "tcs": tcs,
        "must_total": len(must), "must_traced": len(traced),
        "trace_coverage": (len(traced) / len(must)) if must else None,
    }


def check(spec: Parsed, plan: Parsed | None, test: Parsed | None, retired_ids: list[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    sp, pl, ts = "spec.md", "plan.md", "test-spec.md"
    issues += _dups(spec.reqs, "REQ", sp)
    if plan:
        issues += _dups(plan.tasks, "TASK", pl)
    if test:
        issues += _dups(test.tcs, "TC", ts)
    req_ids = {r.id for r in spec.reqs}
    req_by_id = {r.id: r for r in spec.reqs}
    tc_ids = {c.id for c in test.tcs} if test else set()

    if not spec.reqs and spec.meta is not None:
        issues.append(blocker("NO_REQUIREMENTS", "spec.md 에 REQ-ID 행이 없음", sp))
    for r in spec.reqs:
        if not r.source:
            issues.append(blocker("NO_SOURCE", f"{r.id} 출처(원천) 없음", sp, r.line))

    if plan:
        for t in plan.tasks:
            if not t.reqs:
                issues.append(err("ORPHAN_TASK", f"{t.id} 가 어떤 REQ 에도 연결되지 않음", pl, t.line))
            for r in t.reqs:
                if r not in req_ids:
                    issues.append(err("UNKNOWN_REF", f"{t.id} 가 존재하지 않는 {r} 참조", pl, t.line))
            for c in t.evidence_tcs:
                if test and c not in tc_ids:
                    issues.append(err("UNKNOWN_REF", f"{t.id} 완료 증거가 존재하지 않는 {c} 참조", pl, t.line))
    if test:
        for c in test.tcs:
            if not c.reqs:
                issues.append(err("ORPHAN_TC", f"{c.id} 가 어떤 REQ 에도 연결되지 않음", ts, c.line))
            for r in c.reqs:
                if r not in req_ids:
                    issues.append(err("UNKNOWN_REF", f"{c.id} 가 존재하지 않는 {r} 참조", ts, c.line))
                elif req_by_id[r].is_open:
                    issues.append(err("ORACLE_FOR_OPEN_REQ",
                                      f"{c.id} 가 미결정 요구 {r} 의 기대값을 확정함 — 사용자 결정 전 합격 기준 금지",
                                      ts, c.line))

    if plan is not None and test is not None:
        idx = build_index(spec, plan, test)
        for rid, v in idx["reqs"].items():
            if not v["must"]:
                continue
            if not v["tasks"]:
                issues.append(blocker("MISSING_TASK", f"필수 {rid} 에 연결된 TASK 없음", pl))
            if not v["tcs"]:
                issues.append(blocker("MISSING_TC", f"필수 {rid} 에 연결된 TC 없음", ts))

    current = req_ids | ({t.id for t in plan.tasks} if plan else set()) | tc_ids
    for rid in sorted(set(retired_ids or []) & current):
        issues.append(err("ID_REUSED", f"{rid} 는 삭제된 ID — 재사용 금지 (설계서 §5.1)"))
    return issues
