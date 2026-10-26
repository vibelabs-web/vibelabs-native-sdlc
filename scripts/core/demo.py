"""행사 신청 데모 변경 생성 (`sdlc demo-init`). examples/event-registration/ 원본은 수정하지 않고 복사만 한다."""
from __future__ import annotations

import shutil

from core.changes import HARNESS_ROOT, Project
from core.util import SdlcError, atomic_write_text

EXAMPLE = HARNESS_ROOT / "examples" / "event-registration"
DEMO_ID = "CHG-DEMO-001"

INTERFACE_SECTION = """
## Interfaces and data contracts
- 공개 계약(데모 확정 범위): `Event(capacity=30)` — `register(name) -> "confirmed" | "waitlisted"`,
  `cancel(name)`, `confirmed() -> list[str]`(확정 순), `waitlist() -> list[str]`(대기 순).
- QC 수용 테스트는 이 공개 계약만 사용한다. 내부 자료구조·함수에 기대값을 묶지 않는다.
- 중복 신청 시 반환값: **미결정** (OPEN) — 합격 기준 없음.
"""


def _copy_text(src, dest, change_id: str, append: str = "") -> None:
    text = src.read_text(encoding="utf-8").replace(DEMO_ID, change_id)
    atomic_write_text(dest, text + append)


def init(project: Project, change_id: str | None = None):
    app_dest = project.root / "app"
    if app_dest.exists():
        raise SdlcError(f"{app_dest} 이미 존재 — 덮어쓰지 않습니다")
    ch = project.create("행사 신청 및 대기자 자동 관리", "standard", [], "examples/event-registration",
                        change_id=change_id)
    shutil.copytree(EXAMPLE / "app", app_dest, ignore=shutil.ignore_patterns("__pycache__"))
    _copy_text(EXAMPLE / "intent.md", ch.path("intent"), ch.id)
    _copy_text(EXAMPLE / "spec.md", ch.path("spec"), ch.id, INTERFACE_SECTION)
    _copy_text(EXAMPLE / "plan-with-paths.md", ch.path("plan"), ch.id)
    _copy_text(EXAMPLE / "test-spec.md", ch.path("test_spec"), ch.id)
    _copy_text(EXAMPLE / "qc-manifest.json", ch.path("qc_manifest"), ch.id)
    shutil.copytree(EXAMPLE / "qc-tests", ch.qc_tests_dir, ignore=shutil.ignore_patterns("__pycache__"))
    gi = project.root / ".gitignore"
    if not gi.exists():
        atomic_write_text(gi, "__pycache__/\n*.pyc\n")
    ch.record("demo_init", source=str(EXAMPLE.relative_to(HARNESS_ROOT)))
    ch.save()
    return ch
