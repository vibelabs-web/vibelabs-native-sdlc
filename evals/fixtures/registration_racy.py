"""회귀 픽스처: 확인과 추가 사이에 잠금이 없어 동시 신청 시 정원을 넘는 구현 (작업지시서 §4 시나리오 2)."""
import time


class Event:
    def __init__(self, capacity=30):
        self.capacity = capacity
        self._confirmed, self._waitlist = [], []

    def register(self, name):
        if len(self._confirmed) < self.capacity:
            time.sleep(0.001)
            self._confirmed.append(name)
            return "confirmed"
        self._waitlist.append(name)
        return "waitlisted"

    def cancel(self, name):
        if name in self._confirmed:
            self._confirmed.remove(name)
            if self._waitlist:
                self._confirmed.append(self._waitlist.pop(0))
        elif name in self._waitlist:
            self._waitlist.remove(name)

    def confirmed(self):
        return list(self._confirmed)

    def waitlist(self):
        return list(self._waitlist)
