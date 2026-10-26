"""리뷰·릴리스 체크리스트 작성 (`sdlc release`). 어떤 배포 명령도 실행하지 않는다 (작업지시서 Phase 3-7)."""
from __future__ import annotations

from core import gitutil, report
from core.util import atomic_write_text
from validators import check, drift, frontmatter, gate as g


def draft(change) -> dict:
    data = report.build(change)
    rel_gate = g.gate(change, "RELEASE_APPROVED") if change.state["stage"] == "REVIEW_PENDING" else None
    rep = check.validate(change)
    plan = rep.parsed.get("plan")
    d_issues, out_of_plan = drift.check(change, plan) if plan else ([], [])
    open_bugs = [b["id"] for b in data["bugs"] if b["status"] not in ("verified_fixed", "closed")]
    risk = change.state.get("risk_level")
    head = gitutil.head(change.project.root)
    meta = {"change_id": change.id, "revision": "0.1.0", "status": "draft", "author_role": "release-auditor",
            "source_refs": [data["run_id"]] if data["run_id"] else [], "approval_ref": None}
    review = [
        "# PR Review / Gate (초안 — 승인 아님)", "",
        f"- Change ID: {change.id}",
        f"- PR / 실제 diff SHA: 미확인 / {head or '미확인'}",
        f"- 기준 plan/spec SHA: {data['baselines'].get('plan', '-')} / {data['baselines'].get('spec', '-')}",
        f"- QC report / required CI run: qc-report.md ({data['run_id'] or '미실행'}) / CI 실행 미확인",
        f"- Diff가 Plan을 벗어났는가: {'예 — ' + ', '.join(out_of_plan) if out_of_plan else ('미검증' if any(i.code.startswith('DRIFT_') for i in d_issues) else '아니오')}",
        f"- 미해결 blocker/critical: {', '.join(open_bugs) or '없음'}",
        f"- 위험 등급 및 이유: {risk} {change.state.get('risk_hits') or ''}",
        "- 요구 리뷰어/최종 승인자: 미확인 — 조직 승인 정책(CODEOWNERS/보호 브랜치)에서 지정",
        "- 승인 원본/시간/참조: 없음 (외부 승인 시스템에서만 유효)",
        "- 배포 전 수동 확인: 롤백 런북·스모크 테스트·모니터링 링크 확인 필요",
    ]
    if rel_gate:
        review += ["", f"## RELEASE_APPROVED 게이트 사전 점검: {rel_gate.decision}",
                   *[f"- {i}" for i in rel_gate.reasons], *[f"- 수동 확인: {m}" for m in rel_gate.manual]]
    release = [
        "# Release Record (초안 — 배포는 이 도구가 수행하지 않음)", "",
        f"- Change ID / 릴리스 ID: {change.id} / 미발급",
        f"- PR / 코드 SHA / 빌드 식별자: 미확인 / {head or '미확인'} / 미확인",
        "- 대상 환경: 미확인 (production 은 지정된 인간 승인 필수)",
        f"- 위험도 / 승인자 / 승인 시스템 링크: {risk} / 미확인 / 미확인",
        f"- Pre-deploy 체크/통과 증거: {data['run_id'] or '없음'} (verified_coverage {data['must_verified']}/{data['must_total']})",
        "- 배포 절차 및 담당: 미확인",
        "- 롤백 런북 링크 / 리허설 시점: 미확인",
        "- 배포 후 SLO/스모크 테스트: 미확인",
        "- 배포 결과 / 관측 기간: 미실행",
    ]
    atomic_write_text(change.path("review"), frontmatter.dump(meta) + "\n" + "\n".join(review) + "\n")
    atomic_write_text(change.path("release"), frontmatter.dump(meta) + "\n" + "\n".join(release) + "\n")
    return {"written": ["review.md", "release.md"],
            "release_gate": rel_gate.to_dict() if rel_gate else None}
