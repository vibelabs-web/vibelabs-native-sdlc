"""실행 증거(RUN-NNN.json) 검증 — 고정 SHA·기준선 일치·로그 무결성 (설계서 §5.4, §7)."""
from __future__ import annotations

from pathlib import Path

from core import hashing
from core.util import canonical_json, read_json
from validators import schema
from validators.issues import Issue, err
from validators.paths import PathEscape, safe_join

BASELINE_FIELDS = {"spec_sha": "spec", "test_spec_sha": "test_spec",
                   "qc_manifest_sha": "qc_manifest", "qc_tests_sha": "qc_tests"}


def report_digest(run: dict) -> str:
    return hashing.sha256_bytes(canonical_json({k: v for k, v in run.items() if k != "report_sha256"}).encode())


def run_path(change, run_id: str) -> Path:
    return change.evidence_dir / f"{run_id}.json"


def load_run(change, run_id: str) -> dict | None:
    p = run_path(change, run_id)
    return read_json(p) if p.is_file() else None


def verify(change, run: dict, head: str | None) -> list[Issue]:
    """비어 있으면 게이트에 쓸 수 있는 증거. 하나라도 있으면 그 RUN 은 사용 불가."""
    rid = run.get("run_id", "?")
    f = f"evidence/{rid}.json"
    issues = [err("EVIDENCE_SCHEMA", e, f) for e in schema.validate(run, schema.load("evidence"))]
    if issues:
        return issues
    if run["report_sha256"] != report_digest(run):
        issues.append(err("EVIDENCE_TAMPERED", f"{rid} 내용이 기록 이후 변경됨 (report_sha256 불일치)", f))
    if run["change_id"] != change.id:
        issues.append(err("EVIDENCE_WRONG_CHANGE", f"{rid} 는 {run['change_id']} 의 증거", f))
    if not run["commit_sha"]:
        issues.append(err("EVIDENCE_NO_COMMIT", f"{rid} 에 고정 커밋 SHA 없음 — E0 증거로 게이트 불가", f))
    elif head is None:
        issues.append(err("NO_HEAD", "현재 커밋을 확인할 수 없음 — 증거 대조 불가", f))
    elif run["commit_sha"] != head:
        issues.append(err("STALE_EVIDENCE_SHA",
                          f"{rid} 는 {run['commit_sha'][:12]} 에서 실행됨, 현재 HEAD {head[:12]} — 새 SHA 로 재실행 필요", f))
    if run["worktree_dirty"]:
        issues.append(err("EVIDENCE_DIRTY", f"{rid} 는 미커밋 변경이 있는 작업트리에서 실행됨", f))
    if run["verifier_role"] != "qc-verifier":
        issues.append(err("EVIDENCE_ROLE", f"{rid} 실행 역할 {run['verifier_role']} ≠ qc-verifier", f))
    baselines = change.state.get("baselines", {})
    for field, art in BASELINE_FIELDS.items():
        if baselines.get(art) != run.get(field):
            issues.append(err("STALE_EVIDENCE_BASELINE",
                              f"{rid} 의 {art} 해시가 현재 승인 기준선과 다름 — 이전 기준선 증거 재사용 금지", f))
    for c in run["commands"]:
        try:
            lp = safe_join(change.dir, c["log_path"])
        except PathEscape as e:
            issues.append(err("EVIDENCE_PATH", str(e), f))
            continue
        if hashing.sha256_file(lp) != c["log_sha256"]:
            issues.append(err("EVIDENCE_LOG_MISMATCH", f"{c['log_path']} 가 없거나 변경됨", f))
    return issues
