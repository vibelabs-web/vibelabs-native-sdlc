"""골든 데이터셋 검사: qc-tests/golden/GD-NNN.json (입력·기대값 쌍).

파일은 qc-tests/ 아래에 있으므로 기존 BASELINE 해시·qc_lock 이 그대로 잠근다.
개인정보 패턴 검사는 보조 수단이다 — 통과가 실제 개인정보 부재를 보장하지 않는다. 원칙은 합성 데이터다.
"""
from __future__ import annotations

import json
import re

from core.util import read_json
from validators import schema
from validators.issues import Issue, blocker, err, warn

GOLDEN_DIR = "golden"
REQUIRED_RISKS = {"standard", "high"}

_RRN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")
_PHONE = re.compile(r"(?<!\d)01[016789][- ]?(\d{3,4})[- ]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_RESERVED_DOMAINS = {"example.com", "example.org", "example.net"}
_RESERVED_TLDS = {"example", "test", "invalid", "localhost"}


def _pii_hits(text: str) -> list[str]:
    hits = []
    if _RRN.search(text):
        hits.append("주민등록번호 형식")
    # 가운데 자리가 모두 0 인 번호는 관례상의 가짜 번호로 본다
    if any(set(m.group(1)) != {"0"} for m in _PHONE.finditer(text)):
        hits.append("휴대전화번호 형식")
    for m in _EMAIL.finditer(text):
        domain = m.group(1).lower()
        if domain not in _RESERVED_DOMAINS and domain.rsplit(".", 1)[-1] not in _RESERVED_TLDS:
            hits.append(f"이메일({domain})")
    return hits


def load_cases(change) -> tuple[list[dict], list[Issue]]:
    d = change.qc_tests_dir / GOLDEN_DIR
    if not d.is_dir():
        return [], []
    cases, issues = [], []
    golden_schema = schema.load("golden-case")
    for p in sorted(d.glob("*.json")):
        rel = f"qc-tests/{GOLDEN_DIR}/{p.name}"
        try:
            doc = read_json(p)
        except ValueError as e:
            issues.append(err("GOLDEN_SCHEMA", f"JSON 파싱 실패: {e}", rel))
            continue
        errs = schema.validate(doc, golden_schema)
        issues += [err("GOLDEN_SCHEMA", e, rel) for e in errs]
        if errs:
            continue
        if doc["id"] != p.stem:
            issues.append(err("GOLDEN_SCHEMA", f"id {doc['id']} 가 파일명 {p.stem} 와 다름", rel))
        if not doc["req_ids"] or not doc["tc_ids"]:
            issues.append(err("GOLDEN_SCHEMA", "req_ids·tc_ids 는 비어 있을 수 없음", rel))
        hits = _pii_hits(json.dumps(doc, ensure_ascii=False))
        if hits:
            issues.append(blocker("GOLDEN_PII_SUSPECT",
                                  f"{doc['id']}: 개인정보 의심 {hits} — 합성 데이터로 교체 (이메일은 example.com 등 예약 도메인)", rel))
        cases.append({**doc, "_rel": rel})
    return cases, issues


def _check_refs(cases: list[dict], index: dict, manifest: dict | None) -> list[Issue]:
    issues: list[Issue] = []
    mapped = {c["tc_id"] for c in (manifest or {}).get("cases", [])}
    for g in cases:
        for r in g["req_ids"]:
            req = index["reqs"].get(r)
            if req is None:
                issues.append(err("GOLDEN_UNKNOWN_REF", f"{g['id']}: {r} 가 spec 에 없음", g["_rel"]))
            elif req["open"]:
                issues.append(err("GOLDEN_UNKNOWN_REF", f"{g['id']}: 미결정 {r} 에 기대값을 만들 수 없음", g["_rel"]))
        for t in g["tc_ids"]:
            tc = index["tcs"].get(t)
            if tc is None:
                issues.append(err("GOLDEN_UNKNOWN_REF", f"{g['id']}: {t} 가 test-spec 에 없음", g["_rel"]))
            elif not set(tc["reqs"]) & set(g["req_ids"]):
                issues.append(err("GOLDEN_UNKNOWN_REF", f"{g['id']}: {t} 가 {g['req_ids']} 를 검증하지 않음", g["_rel"]))
            elif manifest is not None and t not in mapped:
                issues.append(err("GOLDEN_UNKNOWN_REF", f"{g['id']}: {t} 실행 명령이 qc-manifest 에 없음", g["_rel"]))
    return issues


def _is_used(change) -> bool:
    d = change.qc_tests_dir
    for p in d.rglob("*"):
        if not p.is_file() or GOLDEN_DIR in p.relative_to(d).parts or "__pycache__" in p.parts:
            continue
        if GOLDEN_DIR in p.read_text(encoding="utf-8", errors="replace"):
            return True
    return False


def check(change, index: dict | None, manifest: dict | None) -> list[Issue]:
    cases, issues = load_cases(change)
    if index is None:
        return issues
    issues += _check_refs(cases, index, manifest)
    if cases and not _is_used(change):
        issues.append(warn("GOLDEN_UNUSED", "qc-tests 의 어떤 테스트도 golden 을 참조하지 않음 — 데이터가 판정에 쓰이는지 확인",
                           f"qc-tests/{GOLDEN_DIR}"))
    # 이미 승인된 기준선에는 소급하지 않는다 (reopen 하면 baselines 가 비워져 다시 적용된다)
    if change.state.get("risk_level") in REQUIRED_RISKS and "qc_tests" not in (change.state.get("baselines") or {}):
        covered = {r for g in cases for r in g["req_ids"]}
        for rid, v in index["reqs"].items():
            if v["must"] and not v["open"] and rid not in covered:
                issues.append(blocker("GOLDEN_MISSING",
                                      f"필수 {rid} 에 골든 케이스 없음 — qc-tests/{GOLDEN_DIR}/GD-NNN.json 작성",
                                      "test-spec.md"))
    return issues
