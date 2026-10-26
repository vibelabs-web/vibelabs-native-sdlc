"""`.sdlc/changes/{change_id}/` 생성·조회와 산출물 경로."""
from __future__ import annotations

import re
from pathlib import Path

from core import hashing
from core.util import SdlcError, atomic_write_json, atomic_write_text, now_iso, read_json, today_compact

HARNESS_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = HARNESS_ROOT / "templates"

CHANGE_ID_RE = re.compile(r"^CHG-(\d{8}-\d{3}|DEMO-\d{3})$")

ARTIFACT_FILES = {
    "intent": "intent.md",
    "spec": "spec.md",
    "plan": "plan.md",
    "test_spec": "test-spec.md",
    "qc_manifest": "qc-manifest.json",
    "traceability": "traceability.md",
    "qc_report": "qc-report.md",
    "review": "review.md",
    "release": "release.md",
    "incident": "incident.md",
    "decisions": "decisions.md",
}
QC_TESTS_DIR = "qc-tests"

TEMPLATE_FOR = {
    "intent": ("intent.md", "originator"),
    "spec": ("spec.md", "spec-writer"),
    "plan": ("plan.md", "planner"),
    "test_spec": ("test-spec.md", "qc-architect"),
    "traceability": ("traceability.md", "qc-architect"),
    "qc_report": ("qc-report.md", "qc-verifier"),
    "review": ("review.md", "release-auditor"),
    "release": ("release.md", "release-auditor"),
    "incident": ("incident.md", "operator"),
}

SCHEMA_VERSION = "1.0"


class Change:
    def __init__(self, project: "Project", change_id: str):
        self.project = project
        self.id = change_id
        self.dir = project.changes_dir / change_id
        self.state_path = self.dir / "state.json"
        if not self.state_path.is_file():
            raise SdlcError(f"변경 {change_id} 이 없습니다 ({self.state_path})")
        self.state = read_json(self.state_path)

    def path(self, artifact: str) -> Path:
        return self.dir / ARTIFACT_FILES[artifact]

    @property
    def qc_tests_dir(self) -> Path:
        return self.dir / QC_TESTS_DIR

    @property
    def evidence_dir(self) -> Path:
        return self.dir / "evidence"

    @property
    def issues_dir(self) -> Path:
        return self.dir / "issues"

    def artifact_sha(self, artifact: str) -> str | None:
        if artifact == "qc_tests":
            return qc_tests_digest(self.qc_tests_dir)
        return hashing.git_blob_sha(self.path(artifact))

    def save(self) -> None:
        self.state["updated_at"] = now_iso()
        atomic_write_json(self.state_path, self.state)

    def record(self, event: str, **detail) -> None:
        self.state.setdefault("history", []).append({"at": now_iso(), "event": event, **detail})

    def next_counter(self, name: str) -> int:
        counters = self.state.setdefault("counters", {})
        counters[name] = counters.get(name, 0) + 1
        return counters[name]


def qc_tests_digest(d: Path) -> str | None:
    if not d.is_dir():
        return None
    lines = []
    for p in sorted(d.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            lines.append(f"{p.relative_to(d).as_posix()}:{hashing.git_blob_sha(p)}")
    return hashing.sha256_bytes("\n".join(lines).encode())


class Project:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.sdlc_dir = self.root / ".sdlc"
        self.changes_dir = self.sdlc_dir / "changes"

    @classmethod
    def discover(cls, start: Path | None = None) -> "Project":
        cur = (start or Path.cwd()).resolve()
        for d in [cur, *cur.parents]:
            if (d / ".sdlc").is_dir() or (d / ".git").exists():
                return cls(d)
        return cls(cur)

    def change_ids(self) -> list[str]:
        if not self.changes_dir.is_dir():
            return []
        return sorted(p.name for p in self.changes_dir.iterdir() if (p / "state.json").is_file())

    def load(self, change_id: str) -> Change:
        if not CHANGE_ID_RE.match(change_id):
            raise SdlcError(f"변경 ID 형식 오류: {change_id} (CHG-YYYYMMDD-NNN)")
        return Change(self, change_id)

    def next_change_id(self) -> str:
        day = today_compact()
        nums = [int(c.rsplit("-", 1)[1]) for c in self.change_ids() if c.startswith(f"CHG-{day}-")]
        return f"CHG-{day}-{(max(nums) + 1 if nums else 1):03d}"

    def create(self, title: str, risk_level: str, risk_hits: list[str], source: str | None,
               change_id: str | None = None) -> Change:
        cid = change_id or self.next_change_id()
        d = self.changes_dir / cid
        if d.exists():
            raise SdlcError(f"{cid} 이미 존재")
        d.mkdir(parents=True)
        state = {
            "schema_version": SCHEMA_VERSION,
            "change_id": cid,
            "title": title,
            "stage": "INTAKE",
            "risk_level": risk_level,
            "risk_hits": risk_hits,
            "source_refs": [source] if source else [],
            "created_at": now_iso(),
            "baselines": {},
            "approvals": {},
            "qc_lock": {},
            "build_base_sha": None,
            "build_checks": [],
            "last_verification_run": None,
            "retry_budget": {"per_defect": 3},
            "blocked_reasons": [],
            "known_ids": [],
            "retired_ids": [],
            "counters": {},
            "history": [],
        }
        atomic_write_json(d / "state.json", state)
        ch = Change(self, cid)
        render_template(ch, "intent")
        ch.state["stage"] = "INTENT_DRAFT"
        ch.record("transition", **{"from": "INTAKE", "to": "INTENT_DRAFT", "decision": "ALLOW"})
        ch.save()
        return ch


def render_template(ch: Change, artifact: str, overwrite: bool = False) -> Path:
    if artifact not in TEMPLATE_FOR:
        raise SdlcError(f"템플릿이 없는 산출물: {artifact}")
    tpl_name, role = TEMPLATE_FOR[artifact]
    dest = ch.path(artifact)
    if dest.exists() and not overwrite:
        raise SdlcError(f"{dest.name} 이미 존재 — 덮어쓰지 않습니다")
    text = (TEMPLATES_DIR / tpl_name).read_text(encoding="utf-8").replace("CHG-YYYYMMDD-NNN", ch.id)
    if not text.startswith("---\n"):
        header = (f"---\nchange_id: {ch.id}\nrevision: 0.1.0\nstatus: draft\nauthor_role: {role}\n"
                  f"source_refs: []\napproval_ref: null\n---\n")
        text = header + text
    atomic_write_text(dest, text)
    return dest
