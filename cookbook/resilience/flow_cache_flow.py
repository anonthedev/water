"""
Flow-Level Output Caching Example

Demonstrates caching entire flow outputs so that repeated runs with the
same input skip execution entirely.  Covers basic caching, custom key
functions, cache invalidation, and stats inspection.
"""

import asyncio
import random
from typing import Dict, Any

from water.core import Flow, create_task
from water.resilience import FlowCache, InMemoryFlowCache
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TranslationRequest(BaseModel):
    text: str
    target_lang: str

class TranslationResult(BaseModel):
    original: str
    translated: str
    target_lang: str


# ---------------------------------------------------------------------------
# Simulated expensive task
# ---------------------------------------------------------------------------

api_calls = 0

def translate(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate an expensive translation API call."""
    global api_calls
    api_calls += 1

    data = params["input_data"]
    text = data["text"]
    lang = data["target_lang"]

    # Pretend we called an API
    fake_translation = f"[{lang}] {text[::-1]}"
    print(f"  [API CALL #{api_calls}] Translated to {lang}: {fake_translation}")

    return {
        "original": text,
        "translated": fake_translation,
        "target_lang": lang,
    }


translate_task = create_task(
    id="translate",
    description="Translate text to target language",
    input_schema=TranslationRequest,
    output_schema=TranslationResult,
    execute=translate,
)

translation_flow = Flow(id="translation_flow", description="Cached translation flow")
translation_flow.then(translate_task).register()


# ---------------------------------------------------------------------------
# 1. Basic flow caching
# ---------------------------------------------------------------------------

async def demo_basic_caching():
    print("=== Basic Flow Caching ===\n")

    cache = FlowCache(ttl=60)

    inputs = [
        {"text": "Hello world", "target_lang": "es"},
        {"text": "Hello world", "target_lang": "es"},  # cache hit
        {"text": "Good morning", "target_lang": "fr"},
        {"text": "Hello world", "target_lang": "es"},  # cache hit
    ]

    for inp in inputs:
        cached_result = await cache.get(inp)
        if cached_result is not None:
            print(f"  CACHE HIT for '{inp['text']}' -> {inp['target_lang']}")
            result = cached_result
        else:
            print(f"  CACHE MISS for '{inp['text']}' -> {inp['target_lang']}")
            result = await translation_flow.run(inp)
            await cache.set(inp, result)
        print(f"  Result: {result['translated']}\n")

    stats = cache.get_stats()
    print(f"Hits: {stats.hits}, Misses: {stats.misses}, Hit rate: {stats.hit_rate:.0%}\n")


# ---------------------------------------------------------------------------
# 2. Custom key functions
# ---------------------------------------------------------------------------

async def demo_custom_key_fn():
    print("=== Custom Key Function ===\n")

    # Only use text + target_lang as the key (ignore any extra fields)
    def custom_key(data: Dict[str, Any]) -> str:
        return f"{data['text']}:{data['target_lang']}"

    cache = FlowCache(key_fn=custom_key, ttl=120)

    # These two have different "request_id" but same text+lang -> same key
    inp1 = {"text": "Hi", "target_lang": "de", "request_id": "aaa"}
    inp2 = {"text": "Hi", "target_lang": "de", "request_id": "bbb"}

    result = await translation_flow.run(inp1)
    await cache.set(inp1, result)
    print(f"  Cached result for inp1: {result['translated']}")

    cached = await cache.get(inp2)
    print(f"  Cache lookup for inp2 (different request_id): {'HIT' if cached else 'MISS'}")
    if cached:
        print(f"  Got: {cached['translated']}\n")


# ---------------------------------------------------------------------------
# 3. Cache invalidation
# ---------------------------------------------------------------------------

async def demo_invalidation():
    print("=== Cache Invalidation ===\n")

    cache = FlowCache(ttl=300)
    inp = {"text": "Goodbye", "target_lang": "ja"}

    result = await translation_flow.run(inp)
    await cache.set(inp, result)
    print(f"  Cached: {result['translated']}")

    hit = await cache.get(inp)
    print(f"  Before invalidation: {'HIT' if hit else 'MISS'}")

    removed = await cache.invalidate(inp)
    print(f"  Invalidated: {removed}")

    miss = await cache.get(inp)
    print(f"  After invalidation: {'HIT' if miss else 'MISS'}\n")


# ---------------------------------------------------------------------------
# 4. Stats inspection
# ---------------------------------------------------------------------------

async def demo_stats():
    print("=== Stats Inspection ===\n")

    cache = FlowCache(ttl=60)
    phrases = ["alpha", "beta", "gamma", "alpha", "beta", "alpha"]

    for phrase in phrases:
        inp = {"text": phrase, "target_lang": "it"}
        cached = await cache.get(inp)
        if cached is None:
            result = await translation_flow.run(inp)
            await cache.set(inp, result)

    stats = cache.get_stats()
    print(f"  Total lookups : {stats.hits + stats.misses}")
    print(f"  Hits          : {stats.hits}")
    print(f"  Misses        : {stats.misses}")
    print(f"  Cached entries: {stats.size}")
    print(f"  Hit rate      : {stats.hit_rate:.0%}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    await demo_basic_caching()
    await demo_custom_key_fn()
    await demo_invalidation()
    await demo_stats()


if __name__ == "__main__":
    asyncio.run(main())
