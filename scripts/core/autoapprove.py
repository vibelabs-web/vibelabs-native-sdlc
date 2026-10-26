"""완전 자율 승인 (`sdlc auto-approve`): 게이트 규칙이 통과할 때만 봇 신원으로 PR 을 Approve 한다.

승인 여부는 LLM 의견이 아니라 아래 결정적 조건이다.
1. 대상 게이트를 dry-run 했을 때 error/blocker 가 0 이고,
2. 남은 MANUAL 사유가 "이 스코프(와 짝 스코프)의 승인 레코드 없음" 뿐이며,
3. PR 이 열려 있고 PR head == 로컬 HEAD (승인 대상 내용이 push 되어 있음).
그 뒤 GitHub 리뷰를 다시 검증기로 확인해야 기록된다 (봇은 정책 명단에 있어야 함).
"""
from __future__ import annotations

from core import github, github_app, gitutil
from core.util import SdlcError
from validators import approvals, gate as g

SCOPE_TARGET = {"intent": "INTENT_APPROVED", "spec": "SPEC_APPROVED", "plan_test": "BASELINE_APPROVED",
                "security": "BASELINE_APPROVED", "release": "RELEASE_APPROVED"}
PAIRED = {"plan_test": {"security"}, "security": {"plan_test"}}


class Refused(SdlcError):
    def __init__(self, msg: str, manual: bool = False):
        super().__init__(msg)
        self.manual = manual


def evaluate(change, scope: str) -> g.GateResult:
    """이 스코프의 기존 레코드를 잠시 빼고 dry-run (오래된 승인이 재승인을 막지 않게)."""
    target = SCOPE_TARGET[scope]
    saved = dict(change.state.get("approvals") or {})
    try:
        change.state["approvals"] = {k: v for k, v in saved.items() if k != scope}
        return g.gate(change, target)
    finally:
        change.state["approvals"] = saved


def auto_approve(change, scope: str, pr: int) -> dict:
    if scope not in SCOPE_TARGET:
        raise SdlcError(f"scope 는 {list(SCOPE_TARGET)}")
    res = evaluate(change, scope)
    hard = [i for i in res.reasons if i.severity in ("error", "blocker")]
    if hard:
        raise Refused("게이트 차단 사유가 있어 승인하지 않음:\n" + "\n".join(f"  {i}" for i in hard))
    ok_prefix = tuple(f"{s}: 승인 레코드 없음" for s in {scope} | PAIRED.get(scope, set()))
    other = [m for m in res.manual if not m.startswith(ok_prefix)]
    if other:
        raise Refused("자동 판정할 수 없는 항목이 남아 있음:\n" + "\n".join(f"  {m}" for m in other), manual=True)

    root = change.project.root
    slug = github.repo_slug(root)
    if not slug:
        raise SdlcError("GitHub 원격 없음")
    head = gitutil.head(root)
    pull = github.client().api(f"repos/{slug}/pulls/{pr}")
    if pull.get("state") != "open":
        raise Refused(f"PR #{pr} 가 열려 있지 않음 ({pull.get('state')})")
    pr_head = (pull.get("head") or {}).get("sha")
    if pr_head != head:
        raise Refused(f"PR head {str(pr_head)[:12]} ≠ 로컬 HEAD {str(head)[:12]} — 승인 대상 커밋을 push 하세요")

    bound = g.make_github_record(change, scope, "")["bound"]
    body = "\n".join([
        "<!-- sdlc-harness -->",
        f"**sdlc auto-approve** `{scope}` for `{change.id}` (gate {SCOPE_TARGET[scope]} dry-run: 승인 외 사유 없음)",
        "", "| 대상 | SHA |", "|---|---|",
        *[f"| {k} | `{v}` |" for k, v in bound.items()],
        "", f"risk: {change.state.get('risk_level')} · last run: {change.state.get('last_verification_run') or '-'}",
    ])
    review = github_app.app_client(slug).api(f"repos/{slug}/pulls/{pr}/reviews", "POST",
                                             {"commit_id": head, "event": "APPROVE", "body": body})
    url = review.get("html_url")
    rec = g.make_github_record(change, scope, url)
    vr = approvals.verify(root, change.id, rec)
    rec["approver"] = vr.actor
    if vr.status != approvals.VERIFIED:
        raise Refused(f"봇 리뷰는 남았지만 검증 실패 — 기록하지 않음: {vr.reason} ({url})",
                      manual=vr.status == approvals.UNVERIFIABLE)
    change.state.setdefault("approvals", {})[scope] = rec
    change.record("approval", scope=scope, kind="github_review", ref=url, approver=vr.actor, auto=True)
    change.save()
    return {"scope": scope, "review": url, "approver": vr.actor, "level": vr.level}
