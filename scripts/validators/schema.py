"""JSON Schema 부분 구현 (type/required/properties/enum/pattern/items/minLength/minimum/additionalProperties=false).

외부 의존성(jsonschema) 없이 schemas/*.schema.json 을 검사하기 위한 것이다.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.util import read_json

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

_TYPES = {
    "object": dict, "array": list, "string": str, "integer": int,
    "number": (int, float), "boolean": bool, "null": type(None),
}


def load(name: str) -> dict:
    return read_json(SCHEMAS_DIR / f"{name}.schema.json")


def _type_ok(value, t) -> bool:
    types = t if isinstance(t, list) else [t]
    for name in types:
        py = _TYPES[name]
        if name in ("integer", "number") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate(value, schema: dict, path: str = "$") -> list[str]:
    errs: list[str] = []
    if "type" in schema and not _type_ok(value, schema["type"]):
        return [f"{path}: 타입 {schema['type']} 기대, {type(value).__name__} 받음"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} 는 허용값 {schema['enum']} 아님")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} 가 패턴 {schema['pattern']} 불일치")
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: 길이 {schema['minLength']} 미만")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema:
        if value < schema["minimum"]:
            errs.append(f"{path}: {value} < 최소값 {schema['minimum']}")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: 필수 필드 '{k}' 없음")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs.extend(validate(v, props[k], f"{path}.{k}"))
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: 허용되지 않은 필드 '{k}'")
            elif isinstance(schema.get("additionalProperties"), dict):
                errs.extend(validate(v, schema["additionalProperties"], f"{path}.{k}"))
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errs.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return errs
