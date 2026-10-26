"""최소 YAML frontmatter 파서 (key: value, [a, b], null, true/false, 숫자). 중첩 구조는 지원하지 않는다."""
from __future__ import annotations

import re

_LIST_RE = re.compile(r"^\[(.*)\]$")


def _scalar(v: str):
    v = v.strip()
    if v in ("null", "~", ""):
        return None
    if v in ("true", "false"):
        return v == "true"
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def parse_value(v: str):
    m = _LIST_RE.match(v.strip())
    if m:
        inner = m.group(1).strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    return _scalar(v)


def split(text: str) -> tuple[dict | None, str, list[str]]:
    """반환: (meta 또는 None, body, 파싱 오류 목록)."""
    if not text.startswith("---\n"):
        return None, text, []
    end = text.find("\n---", 4)
    if end < 0:
        return None, text, ["frontmatter 종료 '---' 없음"]
    raw = text[4:end]
    body = text[end + 4:].lstrip("\n")
    meta: dict = {}
    errors: list[str] = []
    for i, line in enumerate(raw.splitlines(), start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            errors.append(f"frontmatter {i}행 파싱 불가: {line!r}")
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = parse_value(v)
    return meta, body, errors


def dump(meta: dict) -> str:
    def fmt(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, list):
            return "[" + ", ".join(fmt(x) for x in v) + "]"
        return str(v)
    return "---\n" + "".join(f"{k}: {fmt(v)}\n" for k, v in meta.items()) + "---\n"


def replace(text: str, meta: dict) -> str:
    _, body, _ = split(text)
    return dump(meta) + "\n" + body
