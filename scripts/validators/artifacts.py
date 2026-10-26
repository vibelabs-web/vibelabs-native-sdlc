"""산출물 파싱(intent/spec/plan/test-spec)과 메타데이터·필수 섹션·자리표시자 검사."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from validators import frontmatter, mdtables, schema
from validators.issues import Issue, blocker, err, warn

REQ_RE = re.compile(r"\bREQ-(?:[A-Z]+-)?\d+\b")
TASK_RE = re.compile(r"\bTASK-\d+\b")
TC_RE = re.compile(r"\bTC-\d+\b")
OPEN_RE = re.compile(r"\bOPEN-\d+\b")
PLACEHOLDER_RE = re.compile(r"<[^<>\n]{1,80}>")

OPEN_STATUS_WORDS = ("open", "미결정", "undecided", "pending", "tbd", "보류")
RESOLVED_RE = re.compile(r"(?<!un)(answered|resolved)|closed|해결|완료|확정|n/a", re.I)
YES_WORDS = ("yes", "y", "예", "차단", "true", "blocking")

INTENT_SECTIONS = ["Problem", "Proposed outcome", "Affected users", "Constraints", "Success signals", "Open questions"]


@dataclass
class Row:
    id: str
    line: int
    cells: dict = field(default_factory=dict)


@dataclass
class Requirement(Row):
    priority: str = "must"
    status: str = ""
    source: str = ""

    @property
    def is_open(self) -> bool:
        return any(w in self.status.lower() for w in OPEN_STATUS_WORDS)

    @property
    def is_must(self) -> bool:
        return self.priority.lower() in ("must", "필수", "") and not self.is_open


@dataclass
class Task(Row):
    reqs: list = field(default_factory=list)
    files: str = ""
    evidence_tcs: list = field(default_factory=list)


@dataclass
class TestCase(Row):
    reqs: list = field(default_factory=list)
    priority: str = "must"
    then: str = ""


@dataclass
class OpenItem(Row):
    blocking: bool = False
    resolved: bool = False


@dataclass
class Parsed:
    path: Path
    meta: dict | None
    body: str
    issues: list[Issue] = field(default_factory=list)
    reqs: list[Requirement] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    tcs: list[TestCase] = field(default_factory=list)
    opens: list[OpenItem] = field(default_factory=list)


def _id_rows(table: mdtables.Table, rx: re.Pattern) -> list[tuple[str, list[str], int]]:
    out = []
    for n, row in enumerate(table.rows):
        first = row[0] if row else ""
        m = rx.fullmatch(first.strip().strip("`*"))
        if m:
            out.append((m.group(0), row, table.line + 2 + n))
    return out


def _clean(cell: str) -> str:
    return "" if PLACEHOLDER_RE.fullmatch(cell.strip()) else cell.strip()


def parse_file(path: Path, kind: str, change_id: str | None = None) -> Parsed:
    rel = path.name
    if not path.is_file():
        return Parsed(path, None, "", [blocker("MISSING_ARTIFACT", f"{rel} 없음", rel)])
    text = path.read_text(encoding="utf-8")
    meta, body, fm_errs = frontmatter.split(text)
    p = Parsed(path, meta, body)
    p.issues += [err("FRONTMATTER_PARSE", e, rel) for e in fm_errs]
    if meta is None:
        p.issues.append(err("FRONTMATTER_MISSING", "frontmatter 없음 (설계서 §5.1 필수 메타데이터)", rel))
    else:
        for e in schema.validate(meta, schema.load("artifact-meta")):
            p.issues.append(err("META_SCHEMA", e, rel))
        if change_id and meta.get("change_id") not in (None, change_id):
            p.issues.append(err("META_CHANGE_ID", f"change_id {meta.get('change_id')} ≠ 폴더 {change_id}", rel))
        if meta.get("status") == "approved":
            p.issues.append(warn("STATUS_NOT_EVIDENCE",
                                 "문서의 status: approved 는 승인 증거가 아님 — 게이트는 승인 검증기만 신뢰", rel))
    tables = mdtables.parse(body)
    offset = text[: len(text) - len(body)].count("\n")
    for t in tables:
        t.line += offset
    _parse_tables(p, tables, kind, rel)
    _check_placeholders(p, body, offset, rel)
    if kind == "intent":
        for sec in INTENT_SECTIONS:
            if not re.search(rf"^##\s+.*{re.escape(sec)}", body, re.M | re.I):
                p.issues.append(blocker("INTENT_SECTION", f"필수 섹션 '{sec}' 없음", rel))
    return p


def _parse_tables(p: Parsed, tables: list[mdtables.Table], kind: str, rel: str) -> None:
    for t in tables:
        if kind == "spec":
            pr, st, src = t.col("우선순위", "priority"), t.col("상태", "status"), t.col("원천", "출처", "source")
            for rid, row, line in _id_rows(t, REQ_RE):
                p.reqs.append(Requirement(rid, line, priority=_clean(t.cell(row, pr)) or "must",
                                          status=_clean(t.cell(row, st)), source=_clean(t.cell(row, src))))
        if kind == "plan":
            rq, fc, ev = t.col("REQ"), t.col("변경 파일", "파일", "file", "컴포넌트"), t.col("완료 증거", "evidence")
            for tid, row, line in _id_rows(t, TASK_RE):
                p.tasks.append(Task(tid, line, reqs=REQ_RE.findall(t.cell(row, rq)),
                                    files=_clean(t.cell(row, fc)), evidence_tcs=TC_RE.findall(t.cell(row, ev))))
        if kind == "test_spec":
            rq, pr, th = t.col("REQ"), t.col("우선순위", "priority"), t.col("기대 결과", "then")
            for cid, row, line in _id_rows(t, TC_RE):
                p.tcs.append(TestCase(cid, line, reqs=REQ_RE.findall(t.cell(row, rq)),
                                      priority=_clean(t.cell(row, pr)) or "must", then=_clean(t.cell(row, th))))
        bl, stc = t.col("차단"), t.col("상태", "처리 상태", "status")
        for oid, row, line in _id_rows(t, OPEN_RE):
            b = t.cell(row, bl).strip().lower()
            s = t.cell(row, stc).lower()
            p.opens.append(OpenItem(oid, line, blocking=b in YES_WORDS,
                                    resolved=bool(RESOLVED_RE.search(s)) and "미해결" not in s))


def _check_placeholders(p: Parsed, body: str, offset: int, rel: str) -> None:
    for n, line in enumerate(body.splitlines(), start=offset + 1):
        if line.lstrip().startswith("<!--"):
            continue
        for m in PLACEHOLDER_RE.finditer(line):
            p.issues.append(blocker("PLACEHOLDER", f"채워지지 않은 자리표시자 {m.group(0)}", rel, n))
