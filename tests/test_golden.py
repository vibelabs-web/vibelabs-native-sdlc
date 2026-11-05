"""골든 데이터셋 검사: 등급별 필수·스키마·참조·개인정보 패턴·기준선 잠금."""
import json
import shutil

from _base import SandboxCase, fx

from validators import check, gate as g, golden


def case(gid="GD-009", req="REQ-001", tc="TC-001", **over):
    return {"id": gid, "req_ids": [req], "tc_ids": [tc], "provenance": "synthetic",
            "source_ref": "spec.md", "input": {"a": 1}, "expected": {"b": 2}, **over}


class GoldenTest(SandboxCase):
    def setUp(self):
        super().setUp()
        self.ch = self.sb.demo()
        self.ch.state["stage"] = "PLAN_TEST_DRAFT"
        self.ch.save()
        self.dir = self.ch.qc_tests_dir / "golden"

    def put(self, doc, name=None):
        (self.dir / f"{name or doc['id']}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def validate(self):
        return self.codes(check.validate(self.sb.reload(self.ch)).issues)

    def test_demo_golden_is_clean(self):
        codes = self.validate()
        self.assertFalse(codes & {"GOLDEN_MISSING", "GOLDEN_SCHEMA", "GOLDEN_UNKNOWN_REF", "GOLDEN_PII_SUSPECT", "GOLDEN_UNUSED"})

    def test_missing_blocks_baseline_for_standard_and_high(self):
        shutil.rmtree(self.dir)
        for risk in ("standard", "high"):
            self.ch.state["risk_level"] = risk
            self.ch.save()
            self.assertIn("GOLDEN_MISSING", self.validate(), risk)
        res = g.gate(self.sb.reload(self.ch), "BASELINE_APPROVED")
        self.assertIn("GOLDEN_MISSING", self.codes(res.reasons))

    def test_lite_is_exempt(self):
        shutil.rmtree(self.dir)
        self.ch.state["risk_level"] = "lite"
        self.ch.save()
        self.assertNotIn("GOLDEN_MISSING", self.validate())

    def test_one_case_per_must_req_required(self):
        (self.dir / "GD-003.json").unlink()
        rep = check.validate(self.sb.reload(self.ch))
        hits = [i.message for i in rep.issues if i.code == "GOLDEN_MISSING"]
        self.assertEqual(len(hits), 1)
        self.assertIn("REQ-003", hits[0])

    def test_schema_violations(self):
        bad = case()
        del bad["expected"]
        self.put(bad)
        self.assertIn("GOLDEN_SCHEMA", self.validate())
        self.put(case(), name="GD-009")
        self.put(case(gid="GD-010"), name="GD-011")  # 파일명 불일치
        self.assertIn("GOLDEN_SCHEMA", self.validate())
        (self.dir / "GD-011.json").unlink()
        (self.dir / "GD-012.json").write_text("{not json", encoding="utf-8")
        self.assertIn("GOLDEN_SCHEMA", self.validate())

    def test_unknown_and_mismatched_refs(self):
        for doc in (case(req="REQ-777"), case(tc="TC-777"), case(req="REQ-002", tc="TC-001")):
            self.put(doc)
            self.assertIn("GOLDEN_UNKNOWN_REF", self.validate(), doc)

    def test_pii_patterns(self):
        for value in ("900101-1234567", "010-1234-5678", "kim@realcompany.co.kr"):
            self.put(case(input={"x": value}))
            self.assertIn("GOLDEN_PII_SUSPECT", self.validate(), value)

    def test_reserved_values_allowed(self):
        for value in ("a@example.com", "b@foo.test", "c@bar.invalid", "010-0000-0000"):
            self.assertEqual(golden._pii_hits(value), [], value)

    def test_unused_golden_warns(self):
        qc = self.ch.qc_tests_dir / "test_registration_qc.py"
        qc.write_text(qc.read_text(encoding="utf-8").replace("golden", "data").replace("GOLDEN", "DATA"), encoding="utf-8")
        self.assertIn("GOLDEN_UNUSED", self.validate())


class GoldenLockTest(SandboxCase):
    def test_change_after_baseline_is_detected(self):
        ch = self.sb.demo()
        ch, blocked = fx.advance(self.sb, ch, until="BASELINE_APPROVED")
        self.assertIsNone(blocked)
        f = ch.qc_tests_dir / "golden" / "GD-001.json"
        f.write_text(f.read_text(encoding="utf-8").replace("30", "31"), encoding="utf-8")
        codes = self.codes(check.validate(self.sb.reload(ch)).issues)
        self.assertIn("BASELINE_DRIFT", codes)
        self.assertIn("ORACLE_TAMPERED", codes)

    def test_not_retroactive_after_baseline(self):
        ch = self.sb.demo()
        ch, blocked = fx.advance(self.sb, ch, until="BASELINE_APPROVED")
        self.assertIsNone(blocked)
        self.assertNotIn("GOLDEN_MISSING", self.codes(golden.check(_without_golden(ch), check.validate(ch).index, None)))


def _without_golden(ch):
    class View:
        state = ch.state
        qc_tests_dir = ch.dir / "does-not-exist"
    return View
