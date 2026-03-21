"""
Cookbook: Provider Rate Limiting per Model

Demonstrates how to use ProviderRateLimiter to enforce RPM and TPM
limits on a per-model basis, handle 429 retry-after headers, and
inspect metrics after a batch of requests.
"""

import asyncio
from water.resilience import ProviderRateLimiter, ProviderLimits


async def main():
    # 1. Create a limiter with per-model limits
    limiter = ProviderRateLimiter(
        limits={
            "gpt-4": {"rpm": 10, "tpm": 50_000},
            "claude-3-opus": {"rpm": 20, "tpm": 100_000},
        },
        default_limits=ProviderLimits(rpm=60, tpm=100_000),
    )

    # 2. Acquire permits before calling each provider
    for i in range(5):
        wait = await limiter.acquire("gpt-4", estimated_tokens=500)
        if wait > 0:
            print(f"[gpt-4] request {i+1} waited {wait:.3f}s")
        else:
            print(f"[gpt-4] request {i+1} passed immediately")

    for i in range(3):
        wait = await limiter.acquire("claude-3-opus", estimated_tokens=1000)
        if wait > 0:
            print(f"[claude-3-opus] request {i+1} waited {wait:.3f}s")
        else:
            print(f"[claude-3-opus] request {i+1} passed immediately")

    # 3. Simulate a 429 response and record retry-after
    print("\nSimulating a 429 retry-after of 0.5 seconds for gpt-4...")
    limiter.record_retry_after("gpt-4", 0.5)
    wait = await limiter.acquire("gpt-4", estimated_tokens=200)
    print(f"[gpt-4] post-429 request waited {wait:.3f}s")

    # 4. Adjust limits dynamically
    limiter.set_limits("gpt-4", rpm=30, tpm=80_000)
    print(f"\nUpdated gpt-4 limits: {limiter.get_limits('gpt-4')}")

    # 5. Inspect metrics
    print("\n--- Metrics ---")
    for model, stats in limiter.get_metrics().items():
        print(f"  {model}: {stats}")

    # 6. Reset when done
    limiter.reset()
    print("\nLimiter state reset.")


if __name__ == "__main__":
    asyncio.run(main())
