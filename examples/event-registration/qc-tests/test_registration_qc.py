"""QC 수용 테스트 (QC Architect 소유 — Builder 수정 금지). test-spec.md 의 TC 를 블랙박스로 검증한다.

구현 내부가 아니라 spec 의 공개 계약(Event 의 register/cancel/confirmed/waitlist)만 사용한다.
"""
import json
import os
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(os.environ["SDLC_CHANGE_DIR"]).resolve().parents[2] if "SDLC_CHANGE_DIR" in os.environ \
    else Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "app"))

from registration import Event  # noqa: E402


GOLDEN = Path(__file__).resolve().parent / "golden"


def golden(case_id: str) -> tuple[dict, dict]:
    doc = json.loads((GOLDEN / f"{case_id}.json").read_text(encoding="utf-8"))
    return doc["input"], doc["expected"]


def filled(n: int) -> Event:
    e = Event(capacity=30)
    for i in range(n):
        e.register(f"p{i:02d}")
    return e


class TC001(unittest.TestCase):
    """REQ-001: 29명 확정 상태에서 1명 신청 → 확정 30명 (GD-001)."""
    def test(self):
        given, want = golden("GD-001")
        e = filled(given["confirmed_before"])
        self.assertEqual(e.register(given["register"]), want["result"])
        self.assertEqual(len(e.confirmed()), want["confirmed_count"])
        self.assertEqual(e.waitlist(), want["waitlist"])


class TC002(unittest.TestCase):
    """REQ-002: 30명 확정 상태에서 31번째 신청 → 확정 30명, 대기 1명(1번) (GD-002)."""
    def test(self):
        given, want = golden("GD-002")
        e = filled(given["confirmed_before"])
        self.assertEqual(e.register(given["register"]), want["result"])
        self.assertEqual(len(e.confirmed()), want["confirmed_count"])
        self.assertEqual(e.waitlist(), want["waitlist"])


class TC003(unittest.TestCase):
    """REQ-003: 30명 확정 + 대기 1명에서 참가자 1명 취소 → 확정 30명, 대기 1번 승격 (GD-003)."""
    def test(self):
        given, want = golden("GD-003")
        e = filled(given["confirmed_before"])
        for name in given["waitlist_before"]:
            e.register(name)
        e.cancel(given["cancel"])
        self.assertEqual(len(e.confirmed()), want["confirmed_count"])
        self.assertIn(want["promoted"], e.confirmed())
        self.assertEqual(e.waitlist(), want["waitlist"])


class TC004(unittest.TestCase):
    """REQ-001 동시성: 확정 29명에서 병렬 신청 → 확정 30명 이하 (정해진 반복 횟수)."""
    def test(self):
        for _ in range(20):
            e = filled(29)
            barrier = threading.Barrier(8)

            def go(i):
                barrier.wait()
                e.register(f"c{i}")

            ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertLessEqual(len(e.confirmed()), 30)
            self.assertEqual(len(e.confirmed()) + len(e.waitlist()), 37)


if __name__ == "__main__":
    unittest.main()
