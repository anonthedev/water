"""
Cookbook: Layered Memory Hierarchy
==================================

Demonstrates the layered memory system with ORG > PROJECT > USER > SESSION >
AUTO_LEARNED priority, multiple backends, and agent self-managed memory tools.

Usage:
    python cookbook/agents/memory_flow.py
"""

import asyncio
import tempfile
import os

from water.agents.memory import (
    MemoryLayer,
    MemoryEntry,
    InMemoryBackend,
    FileBackend,
    MemoryManager,
    create_memory_tools,
)


async def main():
    print("=" * 60)
    print("Layered Memory Hierarchy Demo")
    print("=" * 60)

    # -- Example 1: Basic in-memory usage --------------------------------
    print("\n--- Example 1: Basic memory operations ---")
    manager = MemoryManager()

    await manager.add("company_policy", "Always use type hints", MemoryLayer.ORG)
    await manager.add("api_base_url", "https://api.example.com", MemoryLayer.PROJECT)
    await manager.add("preferred_model", "gpt-4", MemoryLayer.USER)
    await manager.add("current_task", "Fix authentication bug", MemoryLayer.SESSION)
    await manager.add("user_prefers_json", "true", MemoryLayer.AUTO_LEARNED)

    entry = await manager.get("company_policy")
    print(f"  ORG memory: {entry.key} = {entry.value}")

    entry = await manager.get("preferred_model")
    print(f"  USER memory: {entry.key} = {entry.value}")

    # -- Example 2: Priority-based lookup --------------------------------
    print("\n--- Example 2: Priority-based lookup ---")
    # Same key in different layers — ORG wins
    await manager.add("timeout", "30s", MemoryLayer.ORG, metadata={"source": "admin"})
    await manager.add("timeout", "10s", MemoryLayer.USER, metadata={"source": "user pref"})
    await manager.add("timeout", "5s", MemoryLayer.SESSION)

    entry = await manager.get("timeout")
    print(f"  'timeout' resolves to: {entry.value} (from {entry.layer.value} layer)")
    assert entry.layer == MemoryLayer.ORG, "ORG should have highest priority"

    # -- Example 3: Search across layers --------------------------------
    print("\n--- Example 3: Search across layers ---")
    results = await manager.search("api")
    print(f"  Search 'api': {[(r.key, r.layer.value) for r in results]}")

    results = await manager.search("timeout")
    print(f"  Search 'timeout': {[(r.key, r.layer.value) for r in results]}")

    # -- Example 4: System prompt generation ----------------------------
    print("\n--- Example 4: System prompt from memories ---")
    prompt = manager.to_system_prompt()
    print(f"  Generated prompt ({len(prompt)} chars):")
    for line in prompt.split("\n")[:8]:
        print(f"    {line}")
    print("    ...")

    # -- Example 5: File-backed memory ----------------------------------
    print("\n--- Example 5: File-backed persistent memory ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_backend = FileBackend(tmpdir)
        file_manager = MemoryManager(default_backend=file_backend)

        await file_manager.add("db_host", "localhost:5432", MemoryLayer.PROJECT)
        await file_manager.add("debug_mode", "true", MemoryLayer.SESSION)

        # Verify persistence by creating a new manager pointing to same dir
        file_backend2 = FileBackend(tmpdir)
        file_manager2 = MemoryManager(default_backend=file_backend2)

        entry = await file_manager2.get("db_host", MemoryLayer.PROJECT)
        print(f"  Persisted & reloaded: {entry.key} = {entry.value}")

        files = os.listdir(tmpdir)
        print(f"  Layer files on disk: {files}")

    # -- Example 6: TTL-based expiration --------------------------------
    print("\n--- Example 6: TTL expiration ---")
    ttl_manager = MemoryManager()
    await ttl_manager.add("temp_token", "abc123", MemoryLayer.SESSION, ttl=0.0)
    # TTL=0 means it expires immediately
    entry = await ttl_manager.get("temp_token", MemoryLayer.SESSION)
    print(f"  Expired entry (TTL=0): {entry}")
    assert entry is None, "Should be expired"

    await ttl_manager.add("long_token", "xyz789", MemoryLayer.SESSION, ttl=3600)
    entry = await ttl_manager.get("long_token", MemoryLayer.SESSION)
    print(f"  Valid entry (TTL=3600): {entry.key} = {entry.value}")

    # -- Example 7: Memory tools for agents -----------------------------
    print("\n--- Example 7: Agent memory tools ---")
    agent_manager = MemoryManager()
    tools = create_memory_tools(agent_manager)
    print(f"  Created {len(tools)} memory tools: {[t.name for t in tools]}")

    # Simulate agent storing a memory
    store_result = await tools[0].run({"key": "user_name", "value": "Alice"})
    print(f"  Store result: {store_result.output}")

    # Simulate agent recalling memories
    recall_result = await tools[1].run({"query": "user"})
    print(f"  Recall result: {recall_result.output}")

    # Simulate agent listing memories
    list_result = await tools[2].run({})
    print(f"  List result: {list_result.output}")

    # -- Example 8: Per-layer backends ----------------------------------
    print("\n--- Example 8: Per-layer backends ---")
    org_backend = InMemoryBackend()
    session_backend = InMemoryBackend()

    multi_manager = MemoryManager(
        backends={
            MemoryLayer.ORG: org_backend,
            MemoryLayer.SESSION: session_backend,
        },
        default_backend=InMemoryBackend(),
    )

    await multi_manager.add("rule", "No PII in logs", MemoryLayer.ORG)
    await multi_manager.add("tab_size", "4", MemoryLayer.SESSION)
    await multi_manager.add("feature_flag", "v2_enabled", MemoryLayer.PROJECT)

    all_entries = await multi_manager.get_all()
    print(f"  Total entries across all layers: {len(all_entries)}")
    for e in all_entries:
        print(f"    [{e.layer.value}] {e.key} = {e.value}")

    print("\nAll examples passed!")


if __name__ == "__main__":
    asyncio.run(main())
