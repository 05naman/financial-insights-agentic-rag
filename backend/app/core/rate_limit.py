import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-memory per-key limiter. Fine for a single process; swap for Redis to scale out."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def retry_after(self, key: str) -> int:
        """Whole seconds until the oldest hit leaves the window (at least 1)."""
        q = self._hits[key]
        if not q:
            return 1
        return max(1, int(self.window - (time.monotonic() - q[0])) + 1)
