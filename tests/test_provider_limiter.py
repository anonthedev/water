import asyncio
import time
import pytest
from water.resilience.provider_limiter import (
    ProviderLimits,
    LimiterMetrics,
    ProviderRateLimiter,
)


def test_provider_limits_defaults():
    limits = ProviderLimits()
    assert limits.rpm == 60
    assert limits.tpm == 100_000


def test_provider_limits_custom():
    limits = ProviderLimits(rpm=120, tpm=200_000)
    assert limits.rpm == 120
    assert limits.tpm == 200_000


def test_set_and_get_limits():
    limiter = ProviderRateLimiter()
    limiter.set_limits("gpt-4", rpm=30, tpm=50_000)
    limits = limiter.get_limits("gpt-4")
    assert limits.rpm == 30
    assert limits.tpm == 50_000


def test_default_limits_used_when_model_not_configured():
    default = ProviderLimits(rpm=10, tpm=5_000)
    limiter = ProviderRateLimiter(default_limits=default)
    limits = limiter.get_limits("unknown-model")
    assert limits.rpm == 10
    assert limits.tpm == 5_000


@pytest.mark.asyncio
async def test_acquire_without_throttling():
    limiter = ProviderRateLimiter()
    wait = await limiter.acquire("gpt-4")
    assert wait == 0.0
    assert limiter.metrics["gpt-4"].total_requests == 1
    assert limiter.metrics["gpt-4"].throttled_requests == 0


@pytest.mark.asyncio
async def test_acquire_with_rpm_throttling():
    limiter = ProviderRateLimiter()
    limiter.set_limits("gpt-4", rpm=2, tpm=100_000)
    # First two requests should go through without throttling
    w1 = await limiter.acquire("gpt-4")
    w2 = await limiter.acquire("gpt-4")
    assert w1 == 0.0
    assert w2 == 0.0
    # Third request should be throttled (rpm=2 exceeded)
    w3 = await limiter.acquire("gpt-4")
    assert w3 > 0.0
    assert limiter.metrics["gpt-4"].throttled_requests >= 1


@pytest.mark.asyncio
async def test_record_retry_after():
    limiter = ProviderRateLimiter()
    limiter.record_retry_after("gpt-4", 0.1)
    start = time.monotonic()
    wait = await limiter.acquire("gpt-4")
    elapsed = time.monotonic() - start
    assert wait > 0.0
    assert elapsed >= 0.05  # allow some tolerance


def test_get_metrics_specific_model():
    limiter = ProviderRateLimiter()
    # Before any requests, metrics should show zeros
    m = limiter.get_metrics("gpt-4")
    assert m["model"] == "gpt-4"
    assert m["total_requests"] == 0
    assert m["throttled"] == 0
    assert m["avg_wait"] == 0.0


@pytest.mark.asyncio
async def test_get_metrics_all_models():
    limiter = ProviderRateLimiter()
    await limiter.acquire("gpt-4")
    await limiter.acquire("claude")
    all_metrics = limiter.get_metrics()
    assert "gpt-4" in all_metrics
    assert "claude" in all_metrics
    assert all_metrics["gpt-4"]["total_requests"] == 1
    assert all_metrics["claude"]["total_requests"] == 1


@pytest.mark.asyncio
async def test_reset_clears_state():
    limiter = ProviderRateLimiter()
    await limiter.acquire("gpt-4")
    assert limiter.metrics["gpt-4"].total_requests == 1
    limiter.reset()
    assert len(limiter.metrics) == 0
    assert len(limiter._request_timestamps) == 0
    assert len(limiter._token_usage) == 0
    assert len(limiter._retry_after) == 0


def test_limiter_metrics_avg_wait_time():
    m = LimiterMetrics(total_requests=0, throttled_requests=0, total_wait_time=0.0)
    assert m.avg_wait_time == 0.0
    m.total_requests = 4
    m.total_wait_time = 2.0
    assert m.avg_wait_time == 0.5


@pytest.mark.asyncio
async def test_estimated_tokens_tracking():
    limiter = ProviderRateLimiter()
    limiter.set_limits("gpt-4", rpm=100, tpm=500)
    await limiter.acquire("gpt-4", estimated_tokens=200)
    assert len(limiter._token_usage["gpt-4"]) == 1
    _, tokens = limiter._token_usage["gpt-4"][0]
    assert tokens == 200


@pytest.mark.asyncio
async def test_multiple_model_tracking():
    limiter = ProviderRateLimiter()
    limiter.set_limits("gpt-4", rpm=10, tpm=50_000)
    limiter.set_limits("claude", rpm=20, tpm=80_000)
    await limiter.acquire("gpt-4")
    await limiter.acquire("gpt-4")
    await limiter.acquire("claude")
    assert limiter.metrics["gpt-4"].total_requests == 2
    assert limiter.metrics["claude"].total_requests == 1
    assert limiter.get_limits("gpt-4").rpm == 10
    assert limiter.get_limits("claude").rpm == 20


@pytest.mark.asyncio
async def test_constructor_with_limits_dict():
    limiter = ProviderRateLimiter(limits={
        "gpt-4": {"rpm": 15, "tpm": 25_000},
    })
    limits = limiter.get_limits("gpt-4")
    assert limits.rpm == 15
    assert limits.tpm == 25_000
