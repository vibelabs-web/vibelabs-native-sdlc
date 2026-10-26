"""검사 결과 항목.

severity
- error   : 구조적 결함 (중복·미존재 참조·스키마·변조·기준선 드리프트). `validate` 가 비정상 종료.
- blocker : 아직 완성되지 않음 (자리표시자·커버리지 누락·차단 질문). 게이트를 막는다. `validate --strict` 에서 비정상 종료.
- warning : 정보. 판정에 쓰지 않는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def __str__(self) -> str:
        loc = f" ({self.file}{':' + str(self.line) if self.line else ''})" if self.file else ""
        return f"[{self.severity.upper()}] {self.code}: {self.message}{loc}"


def err(code, msg, file=None, line=None) -> Issue:
    return Issue(code, "error", msg, file, line)


def blocker(code, msg, file=None, line=None) -> Issue:
    return Issue(code, "blocker", msg, file, line)


def warn(code, msg, file=None, line=None) -> Issue:
    return Issue(code, "warning", msg, file, line)
