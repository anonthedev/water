import asyncio
import time
from typing import Dict, Optional


class RateLimiter:
    """
    Token-bucket rate limiter for throttling task execution.

    Each named bucket tracks its own token count. Tokens are replenished
    at a fixed rate (max_per_second). acquire() blocks until a token is
    available.
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = {}

    def get_bucket(self, name: str, max_per_second: float) -> "_Bucket":
        """Get or create a named rate-limit bucket."""
        if name not in self._buckets:
            self._buckets[name] = _Bucket(max_per_second)
        return self._buckets[name]

    async def acquire(self, name: str, max_per_second: float) -> None:
        """Wait until the named bucket allows execution."""
        bucket = self.get_bucket(name, max_per_second)
        await bucket.acquire()


class _Bucket:
    """A single token bucket with a fixed refill rate."""

    def __init__(self, max_per_second: float) -> None:
        self.max_per_second = max_per_second
        self.interval = 1.0 / max_per_second
        self.tokens = 1.0
        self.max_tokens = 1.0
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.max_per_second)
            self.last_refill = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return

            wait_time = (1.0 - self.tokens) / self.max_per_second
            self.tokens = 0.0
            await asyncio.sleep(wait_time)
            self.last_refill = time.monotonic()


# Global rate limiter instance shared across all tasks
_global_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _global_rate_limiter
