"""단계 게이트 (설계서 §7). LLM 서술이 아니라 구조화 데이터·승인 검증기·실행 증거만으로 판정한다.

결정
- ALLOW                          : 전이 허용
- BLOCK                          : 규칙 위반 (exit 1)
- MANUAL_VERIFICATION_REQUIRED   : 자동 판정 불가 — 절대 추정 승인하지 않음 (exit 3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core import bugs, gitutil, policy, state as sm
from core.util import now_iso
from validators import approvals, check, drift, evidence, tamper
from validators.issues import Issue, blocker, err

ALLOW, BLOCK, MANUAL = "ALLOW", "BLOCK", "MANUAL_VERIFICATION_REQUIRED"

APPROVAL_GATES = {"INTENT_APPROVED": "intent", "SPEC_APPROVED": "spec",
                  "BASELINE_APPROVED": "plan_test", "RELEASE_APPROVED": "release"}

QC_EVIDENCE_GATES = {"QC_PASSED", "REVIEW_PENDING", "RELEASE_APPROVED"}

# 아직 작성 단계가 오지 않은 산출물의 오류는 앞 단계 승인을 막지 않는다
_PLAN_FILES = {"plan.md", "test-spec.md", "qc-manifest.json"}
LATER_FILES = {
    "INTENT_APPROVED": _PLAN_FILES | {"spec.md"},
    "SPEC_DRAFT": _PLAN_FILES | {"spec.md"},
    "SPEC_APPROVED": _PLAN_FILES,
    "PLAN_TEST_DRAFT": _PLAN_FILES,
}


@dataclass
class GateResult:
    change_id: str
    current: str
    target: str
    decision: str = ALLOW
    reasons: list[Issue] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)
    case_results: dict = field(default_factory=dict)

    def block(self, issue: Issue) -> None:
        self.reasons.append(issue)

    def finalize(self) -> "GateResult":
        if any(i.severity in ("error", "blocker") for i in self.reasons):
            self.decision = BLOCK
        elif self.manual:
            self.decision = MANUAL
        else:
            self.decision = ALLOW
        return self

    def to_dict(self) -> dict:
        return {"change_id": self.change_id, "from": self.current, "to": self.target,
                "decision": self.decision, "reasons": [i.to_dict() for i in self.reasons],
                "manual_verification": self.manual, "case_results": self.case_results}


def required_level(change, scope: str) -> str:
    if scope == "release" or change.state.get("risk_level") == "high":
        return "E2"
    return "E1"


def _prior_scopes(target: str, high: bool = False) -> list[str]:
    idx = sm.STAGES.index(target if target != "DEFECT_OPEN" else "QC_RUNNING")
    scopes = []
    if idx > sm.STAGES.index("INTENT_APPROVED"):
        scopes.append("intent")
    if idx > sm.STAGES.index("SPEC_APPROVED"):
        scopes.append("spec")
    if idx > sm.STAGES.index("BASELINE_APPROVED"):
        scopes.append("plan_test")
        if high:
            scopes.append("security")
    if idx > sm.STAGES.index("RELEASE_APPROVED"):
        scopes.append("release")
    return scopes


def current_bound(change, scope: str) -> dict:
    return {art: change.artifact_sha(art) for art in sm.APPROVAL_SCOPES[scope]}


def make_github_record(change, scope: str, review_url: str) -> dict:
    root = change.project.root
    if scope == "release":
        bound = {"commit": gitutil.head(root), "qc_run": change.state.get("last_verification_run")}
        paths = {}
    else:
        bound = current_bound(change, scope)
        paths = {art: (change.qc_tests_dir if art == "qc_tests" else change.path(art)).relative_to(root).as_posix()
                 for art in bound}
    return {"scope": scope, "kind": "github_review", "ref": review_url, "bound": bound, "paths": paths,
            "at": now_iso()}


def _verify_approval(change, scope: str, res: GateResult) -> str | None:
    """검증되면 승인자(actor)를 돌려준다."""
    rec = (change.state.get("approvals") or {}).get(scope)
    if not rec:
        res.manual.append(f"{scope}: 승인 레코드 없음 — 승인권자가 `sdlc approve {change.id} {scope}` (TTY) 또는 "
                          f"외부 승인 시스템에서 승인해야 함")
        return
    vr = approvals.verify(change.project.root, change.id, rec)
    if vr.status == approvals.INVALID:
        res.block(err("APPROVAL_INVALID", f"{scope}: {vr.reason}"))
        return
    if vr.status == approvals.UNVERIFIABLE:
        res.manual.append(f"{scope}: {vr.reason}")
        return
    need = required_level(change, scope)
    if not approvals.meets(vr.level, need):
        res.manual.append(f"{scope}: 승인 증거 {vr.level} < 필요 {need} "
                          f"({'high-risk' if change.state.get('risk_level') == 'high' else 'release'} 는 "
                          f"외부 신뢰 승인 필요 — 로컬 승인 불인정)")
        return
    if rec.get("scope") != scope:
        res.block(err("APPROVAL_SCOPE", f"{scope} 자리에 {rec.get('scope')} 승인 레코드"))
        return
    for art, sha in (rec.get("bound") or {}).items():
        if art in ("commit", "qc_run"):
            continue
        cur = change.artifact_sha(art)
        if cur != sha:
            res.block(err("APPROVAL_STALE", f"{scope} 승인 후 {art} 변경됨 — 이전 승인 무효, 재리뷰 필요"))
    if scope == "release":
        head = gitutil.head(change.project.root)
        if not gitutil.same_code(change.project.root, (rec.get("bound") or {}).get("commit"), head):
            res.block(err("APPROVAL_STALE", "release 승인 이후 제품 코드가 바뀜 (승인 커밋 → HEAD 에 .sdlc/ 밖 변경) — 승인 무효"))
    return vr.actor or rec.get("approver")


def _verify_security(change, res: GateResult, primary: str | None) -> None:
    """high-risk: plan_test 와 별개로 정책에 등록된 보안/정책 소유자의 외부 승인 (SOP §1)."""
    allowed = policy.allowed_reviewers(change.project.root, "security")
    if not allowed:
        res.manual.append(f"security: high-risk 변경은 {policy.POLICY_REL} 에 security 승인자 명단이 필요")
        return
    actor = _verify_approval(change, "security", res)
    if actor and primary and actor.lower() == primary.lower() and policy.distinct_security_reviewer(change.project.root):
        res.block(err("SECURITY_SAME_REVIEWER", f"security 승인자 {actor} 가 plan_test 승인자와 같음 — 독립 승인 필요"))


def _verify_ci(change, head: str | None, res: GateResult) -> None:
    """E2 증거: 현재 HEAD 에 대한 신뢰 CI 의 필수 체크 성공 (설계서 §5.4)."""
    from core import github
    slug = github.repo_slug(change.project.root)
    if not head or not slug:
        res.manual.append("CI: GitHub 원격/커밋을 확인할 수 없음 — 필수 체크 검증 불가")
        return
    try:
        data = github.client().api(f"repos/{slug}/commits/{head}/check-runs?per_page=100")
    except github.GhUnavailable as e:
        res.manual.append(f"CI: GitHub 확인 불가 ({e})")
        return
    except github.GhError as e:
        res.manual.append(f"CI: {head[:12]} 체크 조회 실패 — push 되지 않은 커밋일 수 있음 ({e.status})")
        return
    runs = data.get("check_runs", []) if isinstance(data, dict) else []
    for name in policy.required_checks(change.project.root):
        # 같은 커밋에 여러 번 돈 경우(리뷰 이벤트 재실행 등) 가장 최근 실행만 본다
        mine = sorted((r for r in runs if r.get("name") == name), key=lambda r: r.get("id", 0))[-1:]
        if not mine:
            res.manual.append(f"CI: {head[:12]} 에 필수 체크 '{name}' 실행 기록 없음")
        elif any(r.get("status") != "completed" for r in mine):
            res.manual.append(f"CI: 필수 체크 '{name}' 아직 실행 중")
        elif not all(r.get("conclusion") == "success" for r in mine):
            res.block(err("CI_CHECK_FAILED", f"필수 체크 '{name}' = {[r.get('conclusion') for r in mine]} @ {head[:12]}"))


def _relevant_blockers(target: str, issues: list[Issue]) -> list[Issue]:
    if target in ("SPEC_DRAFT", "PLAN_TEST_DRAFT", "INTENT_DRAFT"):
        return []
    if target == "INTENT_APPROVED":
        files = {"intent.md"}
    elif target == "SPEC_APPROVED":
        files = {"intent.md", "spec.md"}
    else:
        return [i for i in issues if i.severity == "blocker"]
    return [i for i in issues if i.severity == "blocker" and i.file in files]


def qc_results(change, rep: check.Report, head: str | None, res: GateResult) -> None:
    run_id = change.state.get("last_verification_run")
    if not run_id:
        res.block(blocker("NO_EVIDENCE", "QC 실행 증거 없음 — `sdlc qc run` 필요 (AI 진술은 증거가 아님)"))
        return
    run = evidence.load_run(change, run_id)
    if run is None:
        res.block(err("EVIDENCE_MISSING", f"{run_id}.json 없음"))
        return
    for i in evidence.verify(change, run, head):
        res.block(i)
    results = {c["tc_id"]: c["result"] for c in run.get("cases", [])}
    res.case_results = results
    idx = rep.index or {"reqs": {}}
    for rid, v in idx["reqs"].items():
        if not v["must"]:
            continue
        if not v["tcs"]:
            res.block(blocker("MISSING_TC", f"필수 {rid} 에 TC 없음"))
        for tc in v["tcs"]:
            r = results.get(tc, "NOT_RUN")
            if r != "PASS":
                res.block(blocker("REQ_NOT_VERIFIED", f"필수 {rid} 의 {tc} = {r} — PASS 아님 (skip/미실행은 미검증)"))
    for b in bugs.load_all(change):
        if not b.resolved:
            res.block(blocker("OPEN_DEFECT", f"{b.id} ({b.status}, {b.meta.get('severity')}) 미해결"))


def _incident_closed_loop(change, res: GateResult) -> None:
    p = change.path("incident")
    if not p.is_file():
        res.block(blocker("MISSING_ARTIFACT", "incident.md 없음 — 운영 피드백을 새 Intent 로 연결해야 함"))
        return
    text = p.read_text(encoding="utf-8")
    for label in ("새 Intent ID:", "새 REQ/TC/EVAL 링크:", "담당자/완료 기준:"):
        m = re.search(rf"{re.escape(label)}[ \t]*(\S.*)?$", text, re.M)
        if not m or not (m.group(1) or "").strip():
            res.block(blocker("INCIDENT_LOOP", f"incident.md '{label}' 비어 있음 (G7)"))


def gate(change, target: str) -> GateResult:
    st = change.state
    cur = st.get("stage")
    res = GateResult(change.id, cur, target)
    if target not in sm.STAGES:
        res.block(err("UNKNOWN_STAGE", f"알 수 없는 단계 {target}"))
        return res.finalize()
    if target not in sm.allowed_next(cur):
        res.block(err("INVALID_TRANSITION", f"{cur} → {target} 전이 불가 (허용: {sm.allowed_next(cur)})"))
        return res.finalize()

    rep = check.validate(change)
    later = LATER_FILES.get(target, set())
    for i in rep.errors:
        if i.file not in later:
            res.block(i)
    for i in _relevant_blockers(target, rep.issues):
        res.block(i)

    high = st.get("risk_level") == "high"
    actors = {}
    for scope in _prior_scopes(target, high):
        if scope == "security":
            _verify_security(change, res, actors.get("plan_test"))
        else:
            actors[scope] = _verify_approval(change, scope, res)
    if target in APPROVAL_GATES:
        actors[APPROVAL_GATES[target]] = _verify_approval(change, APPROVAL_GATES[target], res)
    if target == "BASELINE_APPROVED" and high:
        _verify_security(change, res, actors.get("plan_test"))

    head = gitutil.head(change.project.root)
    if target == "QC_RUNNING":
        if head is None:
            res.block(err("NO_HEAD", "git 커밋이 없음 — 고정 SHA 없이 QC 불가"))
        dirty = gitutil.dirty_paths(change.project.root)
        if dirty:
            res.block(blocker("DIRTY_WORKTREE", f"미커밋 변경 {len(dirty)}개 — 커밋 후 고정 SHA 로 QC: {dirty[:5]}"))
        checks = st.get("build_checks") or []
        last = checks[-1] if checks else None
        if (not last or not gitutil.same_code(change.project.root, last.get("commit_sha"), head)
                or last.get("exit_code") != 0 or last.get("dirty")):
            res.block(blocker("NO_BUILD_CHECK", "현재 HEAD 의 Builder 자체 검사(exit 0) 기록 없음 — "
                                                "`sdlc build check <id> -- <cmd>` (G4)"))
        d_issues, _ = drift.check(change, rep.parsed.get("plan"))
        for i in d_issues:
            res.block(i)
        res.reasons += [i for i in tamper.scan_product_tests(change.project.root)]
    if target == "DEFECT_OPEN":
        if not [b for b in bugs.load_all(change) if not b.resolved]:
            res.block(blocker("NO_OPEN_DEFECT", "미해결 BUG 없음 — DEFECT_OPEN 불가"))
    if target == "BUILDING" and cur == "DEFECT_OPEN":
        for b in bugs.load_all(change):
            if b.status in ("escalated", "blocked_spec"):
                res.manual.append(f"{b.id}: {b.status} — 재시도 예산 초과/명세 충돌, 사람의 결정 전 자동 수정 중지")
    if target in QC_EVIDENCE_GATES:
        qc_results(change, rep, head, res)
    if target == "RELEASE_APPROVED" or (high and target == "QC_PASSED"):
        _verify_ci(change, head, res)
    if target == "INTENT_DRAFT" and cur == "MONITORING":
        _incident_closed_loop(change, res)
    return res.finalize()


def apply(change, res: GateResult) -> None:
    """ALLOW 된 게이트를 state 에 반영한다."""
    assert res.decision == ALLOW
    st = change.state
    scope = APPROVAL_GATES.get(res.target)
    if scope and scope != "release":
        for art, sha in current_bound(change, scope).items():
            st.setdefault("baselines", {})[art] = sha
        _update_id_registry(change)
    if res.target == "BASELINE_APPROVED":
        st["qc_lock"] = tamper.make_lock(change)
    if res.target == "BUILDING" and res.current == "BASELINE_APPROVED":
        st["build_base_sha"] = gitutil.head(change.project.root)
    st["stage"] = res.target
    st["blocked_reasons"] = []
    change.record("transition", **{"from": res.current, "to": res.target, "decision": res.decision})
    change.save()


def record_refusal(change, res: GateResult) -> None:
    change.state["blocked_reasons"] = [str(i) for i in res.reasons if i.severity != "warning"] + res.manual
    change.record("gate_refused", to=res.target, decision=res.decision, at=now_iso())
    change.save()


def _update_id_registry(change) -> None:
    rep = check.validate(change)
    ids = set()
    for p in rep.parsed.values():
        ids |= {r.id for r in p.reqs} | {t.id for t in p.tasks} | {c.id for c in p.tcs}
    known = set(change.state.get("known_ids") or [])
    change.state["retired_ids"] = sorted(set(change.state.get("retired_ids") or []) | (known - ids))
    change.state["known_ids"] = sorted(known | ids)
