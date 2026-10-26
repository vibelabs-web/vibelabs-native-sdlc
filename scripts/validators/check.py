"""변경 단위 전체 검사 (`sdlc validate`)."""
from __future__ import annotations

from dataclasses import dataclass, field

from core import bugs, state as sm
from core.util import read_json
from validators import artifacts, schema, tamper, traceability
from validators.issues import Issue, blocker, err, warn
from validators.paths import PathEscape, safe_join


@dataclass
class Report:
    change_id: str
    stage: str
    issues: list[Issue] = field(default_factory=list)
    parsed: dict = field(default_factory=dict)
    index: dict | None = None
    manifest: dict | None = None
    stale: dict = field(default_factory=dict)  # 변경된 산출물 → 무효화 대상

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def blockers(self):
        return [i for i in self.issues if i.severity == "blocker"]

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id, "stage": self.stage,
            "ok": not self.errors, "errors": len(self.errors), "blockers": len(self.blockers),
            "issues": [i.to_dict() for i in self.issues], "stale": self.stale,
            "trace_coverage": self.index["trace_coverage"] if self.index else None,
        }


def _stage_at_least(stage: str, ref: str) -> bool:
    order = sm.STAGES
    if stage == "DEFECT_OPEN":
        stage = "QC_RUNNING"
    return order.index(stage) >= order.index(ref)


def validate(change) -> Report:
    st = change.state
    rep = Report(change.id, st.get("stage", "?"))
    rep.issues += [err("STATE_SCHEMA", e, "state.json") for e in schema.validate(st, schema.load("state"))]
    if st.get("change_id") != change.id:
        rep.issues.append(err("STATE_CHANGE_ID", "state.json change_id 가 폴더명과 다름", "state.json"))
    stage = st.get("stage") if st.get("stage") in sm.STAGES else "INTAKE"

    def want(artifact: str, from_stage: str) -> bool:
        return change.path(artifact).exists() or _stage_at_least(stage, from_stage)

    parsed = {"intent": artifacts.parse_file(change.path("intent"), "intent", change.id)}
    if want("spec", "SPEC_DRAFT"):
        parsed["spec"] = artifacts.parse_file(change.path("spec"), "spec", change.id)
    if want("plan", "PLAN_TEST_DRAFT"):
        parsed["plan"] = artifacts.parse_file(change.path("plan"), "plan", change.id)
    if want("test_spec", "PLAN_TEST_DRAFT"):
        parsed["test_spec"] = artifacts.parse_file(change.path("test_spec"), "test_spec", change.id)
    rep.parsed = parsed
    for p in parsed.values():
        rep.issues += p.issues
        for o in p.opens:
            if o.blocking and not o.resolved:
                rep.issues.append(blocker("OPEN_BLOCKING", f"차단 질문 {o.id} 미해결", p.path.name, o.line))

    if "spec" in parsed and parsed["spec"].meta is not None:
        rep.issues += traceability.check(parsed["spec"], parsed.get("plan"), parsed.get("test_spec"),
                                         st.get("retired_ids"))
        rep.index = traceability.build_index(parsed["spec"], parsed.get("plan"), parsed.get("test_spec"))

    _check_manifest(change, rep, want("qc_manifest", "PLAN_TEST_DRAFT"))
    _check_baselines(change, rep)
    rep.issues += tamper.check(change)
    rep.issues += bugs.validate(change)
    return rep


def _check_manifest(change, rep: Report, wanted: bool) -> None:
    p = change.path("qc_manifest")
    if not p.is_file():
        if wanted:
            rep.issues.append(blocker("MISSING_ARTIFACT", "qc-manifest.json 없음 (TC ↔ 실행 명령)", p.name))
        return
    try:
        man = read_json(p)
    except ValueError as e:
        rep.issues.append(err("MANIFEST_JSON", f"JSON 파싱 실패: {e}", p.name))
        return
    rep.manifest = man
    errs = schema.validate(man, schema.load("qc-manifest"))
    rep.issues += [err("MANIFEST_SCHEMA", e, p.name) for e in errs]
    if errs:
        return
    if man["change_id"] != change.id:
        rep.issues.append(err("MANIFEST_CHANGE_ID", "qc-manifest change_id 불일치", p.name))
    for c in man["cases"]:
        try:
            safe_join(change.project.root, c.get("cwd", "."))
        except PathEscape as e:
            rep.issues.append(err("MANIFEST_PATH", f"{c['tc_id']}: {e}", p.name))
    if rep.index:
        tcs = rep.index["tcs"]
        mapped = {c["tc_id"] for c in man["cases"]}
        for c in mapped - set(tcs):
            rep.issues.append(err("UNKNOWN_REF", f"qc-manifest 의 {c} 가 test-spec 에 없음", p.name))
        must_tcs = {cid for cid, v in tcs.items()
                    if any(rep.index["reqs"].get(r, {}).get("must") for r in v["reqs"])}
        for c in sorted(must_tcs - mapped):
            rep.issues.append(blocker("MISSING_QC_COMMAND", f"필수 {c} 실행 명령이 qc-manifest 에 없음", p.name))


def _check_baselines(change, rep: Report) -> None:
    for art, sha in (change.state.get("baselines") or {}).items():
        cur = change.artifact_sha(art)
        if cur != sha:
            targets = sm.INVALIDATION.get(art, [])
            rep.stale[art] = targets
            rep.issues.append(err("BASELINE_DRIFT",
                                  f"승인 기준선 이후 {art} 변경됨 → 무효화: {', '.join(targets) or '-'}. "
                                  f"`sdlc reopen` 으로 재기준화·재승인 필요", art))
    for scope, rec in (change.state.get("approvals") or {}).items():
        for art, sha in (rec.get("bound") or {}).items():
            if art in ("commit", "qc_run"):
                continue
            if change.artifact_sha(art) != sha:
                rep.issues.append(warn("APPROVAL_STALE", f"{scope} 승인 이후 {art} 변경됨 — 승인 무효", art))
