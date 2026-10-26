"""검증기 단위 테스트: frontmatter·표·경로·스키마·해시·위험 분류."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import _base  # noqa: F401
from core import hashing, risk
from validators import frontmatter, mdtables, paths, schema


class FrontmatterTest(unittest.TestCase):
    def test_parse_values(self):
        meta, body, errs = frontmatter.split("---\na: 1\nb: [X, Y]\nc: null\nd: draft\n---\n# T\n")
        self.assertEqual(meta, {"a": 1, "b": ["X", "Y"], "c": None, "d": "draft"})
        self.assertEqual(body, "# T\n")
        self.assertEqual(errs, [])

    def test_missing_and_broken(self):
        self.assertIsNone(frontmatter.split("# no meta")[0])
        self.assertTrue(frontmatter.split("---\na: 1\n")[2])

    def test_roundtrip(self):
        text = frontmatter.replace("---\na: 1\n---\nbody\n", {"a": 2, "l": ["x"]})
        self.assertEqual(frontmatter.split(text)[0], {"a": 2, "l": ["x"]})


class TableTest(unittest.TestCase):
    def test_parse(self):
        t = mdtables.parse("x\n| A | REQ-ID |\n|---|---|\n| TC-1 | REQ-001 |\n| TC-2 | REQ-002 |\n\n")[0]
        self.assertEqual(t.headers, ["A", "REQ-ID"])
        self.assertEqual(len(t.rows), 2)
        self.assertEqual(t.col("req"), 1)


class PathTest(unittest.TestCase):
    def test_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            (root / "ok.txt").write_text("x")
            self.assertEqual(paths.normalize_rel(root, "./a/../ok.txt"), "ok.txt")
            for bad in ("../x", "/etc/passwd", "~/x", ""):
                with self.assertRaises(paths.PathEscape):
                    paths.safe_join(root, bad)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            outside = Path(d) / "secret"
            outside.mkdir()
            os.symlink(outside, root / "link")
            with self.assertRaises(paths.PathEscape):
                paths.safe_join(root, "link/file")


class SchemaTest(unittest.TestCase):
    def test_subset(self):
        s = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string", "pattern": "^R"},
                                                                 "n": {"type": "integer", "minimum": 1}}}
        self.assertEqual(schema.validate({"a": "R1", "n": 2}, s), [])
        self.assertEqual(len(schema.validate({"a": "X", "n": 0}, s)), 2)
        self.assertTrue(schema.validate({}, s))
        self.assertTrue(schema.validate({"a": "R", "n": True}, s), "bool 은 integer 가 아님")

    def test_schema_files_load(self):
        for n in ("state", "evidence", "bug", "artifact-meta", "qc-manifest"):
            self.assertIn("type", schema.load(n))


class HashTest(unittest.TestCase):
    def test_matches_git(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.md"
            p.write_text("한글 내용\n")
            git = subprocess.run(["git", "hash-object", str(p)], capture_output=True, text=True).stdout.strip()
            self.assertEqual(hashing.git_blob_sha(p), git)


class RiskTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(risk.classify("로그인 인증 추가")[0], "high")
        self.assertEqual(risk.classify("README 오타")[0], "lite")
        self.assertEqual(risk.classify("행사 대기자")[0], "standard")

    def test_no_downgrade(self):
        level, _, warning = risk.resolve("lite", "결제 문구 수정")
        self.assertEqual(level, "high")
        self.assertIsNotNone(warning)


if __name__ == "__main__":
    unittest.main()
