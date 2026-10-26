"""Builder 자체 테스트 (Builder 소유). QC 수용 테스트는 .sdlc/changes/<id>/qc-tests/ 에 따로 있다."""
import unittest

from registration import Event


class SelfTest(unittest.TestCase):
    def test_first_registration_confirmed(self):
        self.assertEqual(Event(capacity=2).register("a"), "confirmed")

    def test_overflow_waitlisted(self):
        e = Event(capacity=1)
        e.register("a")
        self.assertEqual(e.register("b"), "waitlisted")


if __name__ == "__main__":
    unittest.main()
