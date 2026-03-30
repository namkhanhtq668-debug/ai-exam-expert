from __future__ import annotations

import time


class RetryService:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 8.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def next_delay(self, attempt: int) -> float:
        attempt = max(1, attempt)
        delay = self.base_delay * (2 ** (attempt - 1))
        return min(self.max_delay, delay)

    def sleep(self, attempt: int) -> None:
        time.sleep(self.next_delay(attempt))
