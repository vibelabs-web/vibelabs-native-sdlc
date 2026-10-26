"""결함 티켓 (issues/BUG-NNN.md). frontmatter 가 기계 판정의 원본, 본문은 사람용 기록."""
from __future__ import annotations

import re
from pathlib import Path

from core import state as sm
from core.changes import TEMPLATES_DIR
from core.util import SdlcError, atomic_write_text, now_iso
from validators import frontmatter, schema
from validators.issues import Issue, err

BUG_ID_RE = re.compile(r"^BUG-\d{3,}$")


class Bug:
    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        meta, _, errs = frontmatter.split(self.text)
        self.meta = meta or {}
        self.parse_errors = errs if meta is not None else ["frontmatter 없음"]

    @property
    def id(self) -> str:
        return self.meta.get("bug_id", self.path.stem)

    @property
    def status(self) -> str:
        return self.meta.get("status", "")

    @property
    def resolved(self) -> bool:
        return self.status in sm.RESOLVED_BUG_STATES

    def save(self) -> None:
        self.text = frontmatter.replace(self.text, self.meta)
        atomic_write_text(self.path, self.text)

    def add_history(self, role: str, change: str, ref: str) -> None:
        row = f"| {now_iso()} | {role} | {change} | {ref} |"
        lines = self.text.splitlines()
        try:
            h = next(i for i, l in enumerate(lines) if l.strip().startswith("## History"))
        except StopIteration:
            lines += ["", "## History", "| 시각 | 담당 역할 | 상태 변화 | SHA/근거 |", "|---|---|---|---|"]
            h = len(lines) - 3
        j = h + 1
        while j < len(lines) and not lines[j].strip().startswith("|"):
            j += 1
        while j < len(lines) and lines[j].strip().startswith("|"):
            j += 1
        lines.insert(j, row)
        self.text = "\n".join(lines) + "\n"


def load_all(change) -> list[Bug]:
    d = change.issues_dir
    if not d.is_dir():
        return []
    return [Bug(p) for p in sorted(d.glob("BUG-*.md"))]


def get(change, bug_id: str) -> Bug:
    if not BUG_ID_RE.match(bug_id):
        raise SdlcError(f"BUG ID 형식 오류: {bug_id}")
    p = change.issues_dir / f"{bug_id}.md"
    if not p.is_file():
        raise SdlcError(f"{bug_id} 없음")
    return Bug(p)


def validate(change) -> list[Issue]:
    issues = []
    sch = schema.load("bug")
    for b in load_all(change):
        rel = f"issues/{b.path.name}"
        issues += [err("BUG_PARSE", e, rel) for e in b.parse_errors]
        issues += [err("BUG_SCHEMA", e, rel) for e in schema.validate(b.meta, sch)]
        if b.meta.get("change_id") not in (None, change.id):
            issues.append(err("BUG_CHANGE_ID", f"{b.id} change_id 불일치", rel))
    return issues


def create(change, *, req_ids: list[str], tc_ids: list[str], title: str, severity: str,
           expected: str, actual: str, repro: list[str], commit_sha: str | None, run_id: str | None,
           log_ref: str | None, classification: str = "defect") -> Bug:
    n = change.next_counter("bug")
    bug_id = f"BUG-{n:03d}"
    tpl = (TEMPLATES_DIR / "bug.md").read_text(encoding="utf-8")
    _, body, _ = frontmatter.split(tpl)
    body = body.replace("BUG-001", bug_id).replace("<실패 요약>", title)
    body = body.replace("- 기대: <승인 Spec/TC 기준>", f"- 기대: {expected}")
    body = body.replace("- 실제: <증거 관측 결과>", f"- 실제: {actual}")
    body = body.replace("1. 환경/사전 조건:", "1. 환경/사전 조건: " + (repro[0] if repro else "미확인"))
    body = body.replace("2. 단계:", "2. 단계: " + (" → ".join(repro[1:]) if len(repro) > 1 else "미확인"))
    body = body.replace("3. 기대/실제:", f"3. 기대/실제: {expected} / {actual}")
    body = body.replace("- 실제 검증 commit SHA:", f"- 실제 검증 commit SHA: {commit_sha or '미확인'}")
    body = body.replace("- RUN-ID / 로그 / 스크린샷(민감 정보 비포함):",
                        f"- RUN-ID / 로그 / 스크린샷(민감 정보 비포함): {run_id or '-'} / {log_ref or '-'}")
    body = body.replace("- 최초 발견 / 재현 횟수:", f"- 최초 발견 / 재현 횟수: {now_iso()} / 1")
    meta = {
        "bug_id": bug_id, "change_id": change.id, "status": "open", "severity": severity,
        "classification": classification, "requirement_ids": req_ids, "test_ids": tc_ids,
        "fix_attempts": 0, "first_failed_sha": commit_sha, "last_failed_sha": commit_sha,
        "verified_run": None,
    }
    path = change.issues_dir / f"{bug_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, frontmatter.dump(meta) + "\n" + body)
    b = Bug(path)
    b.add_history("qc-verifier", "→ open", f"{run_id or '-'} @ {(commit_sha or '-')[:12]}")
    b.save()
    return b


def transition(change, bug: Bug, to: str, *, role: str, ref: str = "", via_qc: bool = False,
               human: bool = False) -> None:
    cur = bug.status
    if to not in sm.BUG_TRANSITIONS.get(cur, []):
        raise SdlcError(f"{bug.id}: {cur} → {to} 전이 불가 (허용: {sm.BUG_TRANSITIONS.get(cur, [])})")
    if to in sm.QC_ONLY_BUG_TARGETS and not via_qc:
        raise SdlcError(f"{bug.id}: {to} 는 QC 재실행(`sdlc qc run`)만 판정할 수 있음")
    if cur in sm.HUMAN_ONLY_BUG_FROM and not human:
        raise SdlcError(f"{bug.id}: {cur} 해제는 사람의 결정이 필요 (TTY 확인)")
    if to == "ready_for_retest" and role != "builder":
        raise SdlcError("ready_for_retest 는 Builder 가 수정 후 요청한다")
    bug.meta["status"] = to
    bug.add_history(role, f"{cur} → {to}", ref or "-")
    bug.save()
    change.record("bug_transition", bug=bug.id, **{"from": cur, "to": to, "role": role})
