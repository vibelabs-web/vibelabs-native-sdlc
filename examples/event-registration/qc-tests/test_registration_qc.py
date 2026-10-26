"""QC 수용 테스트 (QC Architect 소유 — Builder 수정 금지). test-spec.md 의 TC 를 블랙박스로 검증한다.

구현 내부가 아니라 spec 의 공개 계약(Event 의 register/cancel/confirmed/waitlist)만 사용한다.
"""
import os
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(os.environ["SDLC_CHANGE_DIR"]).resolve().parents[2] if "SDLC_CHANGE_DIR" in os.environ \
    else Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "app"))

from registration import Event  # noqa: E402


def filled(n: int) -> Event:
    e = Event(capacity=30)
    for i in range(n):
        e.register(f"p{i:02d}")
    return e


class TC001(unittest.TestCase):
    """REQ-001: 29명 확정 상태에서 1명 신청 → 확정 30명."""
    def test(self):
        e = filled(29)
        self.assertEqual(e.register("new"), "confirmed")
        self.assertEqual(len(e.confirmed()), 30)


class TC002(unittest.TestCase):
    """REQ-002: 30명 확정 상태에서 31번째 신청 → 확정 30명, 대기 1명(1번)."""
    def test(self):
        e = filled(30)
        self.assertEqual(e.register("w1"), "waitlisted")
        self.assertEqual(len(e.confirmed()), 30)
        self.assertEqual(e.waitlist(), ["w1"])


class TC003(unittest.TestCase):
    """REQ-003: 30명 확정 + 대기 1명에서 참가자 1명 취소 → 확정 30명, 대기 1번 승격."""
    def test(self):
        e = filled(30)
        e.register("w1")
        e.cancel("p05")
        self.assertEqual(len(e.confirmed()), 30)
        self.assertIn("w1", e.confirmed())
        self.assertEqual(e.waitlist(), [])


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
