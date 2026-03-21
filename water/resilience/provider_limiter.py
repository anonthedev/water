# water/resilience/provider_limiter.py
import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List
from collections import deque

@dataclass
class ProviderLimits:
    rpm: int = 60          # requests per minute
    tpm: int = 100_000     # tokens per minute

@dataclass
class LimiterMetrics:
    total_requests: int = 0
    throttled_requests: int = 0
    total_wait_time: float = 0.0

    @property
    def avg_wait_time(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_wait_time / self.total_requests

class ProviderRateLimiter:
    """Token-bucket rate limiter aware of RPM and TPM limits."""

    def __init__(
        self,
        limits: Optional[Dict[str, Dict[str, int]]] = None,
        default_limits: Optional[ProviderLimits] = None,
        respect_retry_after: bool = True,
    ):
        self._limits: Dict[str, ProviderLimits] = {}
        self.respect_retry_after = respect_retry_after
        self.default_limits = default_limits or ProviderLimits()
        self._request_timestamps: Dict[str, deque] = {}
        self._token_usage: Dict[str, deque] = {}  # deque of (timestamp, tokens)
        self._retry_after: Dict[str, float] = {}  # model -> retry_after_timestamp
        self.metrics: Dict[str, LimiterMetrics] = {}

        if limits:
            for model, lim in limits.items():
                self._limits[model] = ProviderLimits(**lim)

    def get_limits(self, model: str) -> ProviderLimits:
        return self._limits.get(model, self.default_limits)

    def set_limits(self, model: str, rpm: int = 60, tpm: int = 100_000) -> None:
        self._limits[model] = ProviderLimits(rpm=rpm, tpm=tpm)

    async def acquire(self, model: str, estimated_tokens: int = 0) -> float:
        """Wait if necessary and return the wait time in seconds."""
        limits = self.get_limits(model)
        if model not in self.metrics:
            self.metrics[model] = LimiterMetrics()
        if model not in self._request_timestamps:
            self._request_timestamps[model] = deque()
            self._token_usage[model] = deque()

        wait_time = 0.0
        now = time.monotonic()

        # Check retry-after
        if model in self._retry_after and now < self._retry_after[model]:
            wait_time = self._retry_after[model] - now
            await asyncio.sleep(wait_time)
            now = time.monotonic()

        # Clean old entries (older than 60 seconds)
        window = 60.0
        while self._request_timestamps[model] and self._request_timestamps[model][0] < now - window:
            self._request_timestamps[model].popleft()
        while self._token_usage[model] and self._token_usage[model][0][0] < now - window:
            self._token_usage[model].popleft()

        # Check RPM
        if len(self._request_timestamps[model]) >= limits.rpm:
            oldest = self._request_timestamps[model][0]
            rpm_wait = window - (now - oldest)
            if rpm_wait > 0:
                wait_time += rpm_wait
                await asyncio.sleep(rpm_wait)
                now = time.monotonic()

        # Check TPM
        current_tokens = sum(t for _, t in self._token_usage[model])
        if estimated_tokens > 0 and current_tokens + estimated_tokens > limits.tpm:
            # Calculate how long until enough tokens expire to fit the new request
            tokens_to_free = (current_tokens + estimated_tokens) - limits.tpm
            freed = 0
            tpm_wait = window  # worst-case: wait for the full window
            for ts, tok in self._token_usage[model]:
                freed += tok
                if freed >= tokens_to_free:
                    # This entry expires at ts + window
                    tpm_wait = (ts + window) - now
                    break
            tpm_wait = max(tpm_wait, 0.0)
            if tpm_wait > 0:
                wait_time += tpm_wait
                await asyncio.sleep(tpm_wait)
                now = time.monotonic()

        # Record
        self._request_timestamps[model].append(now)
        if estimated_tokens > 0:
            self._token_usage[model].append((now, estimated_tokens))

        self.metrics[model].total_requests += 1
        self.metrics[model].total_wait_time += wait_time
        if wait_time > 0:
            self.metrics[model].throttled_requests += 1

        return wait_time

    def record_retry_after(self, model: str, seconds: float) -> None:
        """Record a retry-after header from a 429 response."""
        self._retry_after[model] = time.monotonic() + seconds

    def get_metrics(self, model: str = None) -> Dict[str, Any]:
        if model:
            m = self.metrics.get(model, LimiterMetrics())
            return {"model": model, "total_requests": m.total_requests, "throttled": m.throttled_requests, "avg_wait": m.avg_wait_time}
        return {k: {"total_requests": v.total_requests, "throttled": v.throttled_requests, "avg_wait": v.avg_wait_time} for k, v in self.metrics.items()}

    def reset(self) -> None:
        self._request_timestamps.clear()
        self._token_usage.clear()
        self._retry_after.clear()
        self.metrics.clear()
