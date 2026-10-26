"""Markdown 파이프 표 파서. ID 관계는 표에서 읽는다 (설계서 §5.1)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)
    line: int = 0  # 헤더의 1-based 행 번호

    def col(self, *names: str) -> int | None:
        """헤더에 names 중 하나가 (대소문자 무시) 포함된 첫 열."""
        for i, h in enumerate(self.headers):
            hl = h.lower()
            if any(n.lower() in hl for n in names):
                return i
        return None

    def cell(self, row: list[str], idx: int | None) -> str:
        if idx is None or idx >= len(row):
            return ""
        return row[idx]


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse(text: str) -> list[Table]:
    lines = text.splitlines()
    tables: list[Table] = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].strip().startswith("|") and _SEP_RE.match(lines[i + 1].strip()):
            t = Table(headers=_cells(lines[i]), line=i + 1)
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                t.rows.append(_cells(lines[j]))
                j += 1
            tables.append(t)
            i = j
        else:
            i += 1
    return tables
