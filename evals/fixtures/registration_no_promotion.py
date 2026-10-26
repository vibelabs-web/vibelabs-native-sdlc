"""회귀 픽스처: 취소 시 대기자 승격이 빠진 구현 (작업지시서 §4 시나리오 1)."""
import threading


class Event:
    def __init__(self, capacity=30):
        self.capacity = capacity
        self._confirmed, self._waitlist = [], []
        self._lock = threading.Lock()

    def register(self, name):
        with self._lock:
            if len(self._confirmed) < self.capacity:
                self._confirmed.append(name)
                return "confirmed"
            self._waitlist.append(name)
            return "waitlisted"

    def cancel(self, name):
        with self._lock:
            if name in self._confirmed:
                self._confirmed.remove(name)
            elif name in self._waitlist:
                self._waitlist.remove(name)

    def confirmed(self):
        return list(self._confirmed)

    def waitlist(self):
        return list(self._waitlist)
