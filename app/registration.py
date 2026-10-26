"""행사 신청·대기자 관리 (데모 구현).

공개 계약 (spec.md Interfaces): Event(capacity).register(name) -> "confirmed" | "waitlisted",
cancel(name), confirmed() -> list[str], waitlist() -> list[str].
"""
from __future__ import annotations

import threading


class Event:
    def __init__(self, capacity: int = 30):
        self.capacity = capacity
        self._confirmed: list[str] = []
        self._waitlist: list[str] = []
        self._lock = threading.Lock()

    def register(self, name: str) -> str:
        with self._lock:
            if len(self._confirmed) < self.capacity:
                self._confirmed.append(name)
                return "confirmed"
            self._waitlist.append(name)
            return "waitlisted"

    def cancel(self, name: str) -> None:
        with self._lock:
            if name in self._confirmed:
                self._confirmed.remove(name)
                if self._waitlist:
                    self._confirmed.append(self._waitlist.pop(0))
            elif name in self._waitlist:
                self._waitlist.remove(name)

    def confirmed(self) -> list[str]:
        with self._lock:
            return list(self._confirmed)

    def waitlist(self) -> list[str]:
        with self._lock:
            return list(self._waitlist)
