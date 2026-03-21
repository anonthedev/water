"""
Real-World Cookbook: Claude Code–Style Coding Agent with Water
==============================================================

Builds a coding agent inspired by the Claude Code architecture using Water's
features: sub-agent isolation, layered memory, semantic tool search, and the
ReAct (Think-Act-Observe-Repeat) agentic loop.

Architecture:
  - Orchestrator agent with a ReAct loop
  - Sub-agents for specialised tasks (file ops, code search, testing)
  - Layered memory (org policies, project context, session scratch)
  - Semantic tool selection (picks relevant tools per reasoning step)
  - Tool-call gating via on_tool_call hook
  - Step tracing via on_step hook

Usage:
    python cookbook/real_world/claude_code_agent.py
"""

import asyncio
import json
import tempfile
import os

from water.agents.tools import Tool, Toolkit
from water.agents.react import create_agentic_task
from water.agents.subagent import SubAgentConfig, create_sub_agent_tool
from water.agents.memory import (
    MemoryLayer,
    InMemoryBackend,
    MemoryManager,
    create_memory_tools,
)
from water.agents.tool_search import create_tool_selector


# ============================================================================
# Mock LLM providers (replace with real providers for production)
# ============================================================================

class OrchestratorProvider:
    """Simulates the main orchestrator LLM that plans, delegates, and synthesises."""

    def __init__(self):
        self._step = 0

    async def complete(self, **kwargs):
        self._step += 1
        tools = kwargs.get("tools", [])
        tool_names = [t["function"]["name"] for t in tools]

        if self._step == 1:
            # Step 1: read project memory and plan
            return {
                "content": "Let me check what I know about this project and plan my approach.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "memory_recall",
                            "arguments": {"query": "project conventions"},
                        },
                    },
                ],
            }

        if self._step == 2:
            # Step 2: search for relevant code
            return {
                "content": "I'll search the codebase for the authentication module.",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "function": {
                            "name": "code_search",
                            "arguments": {"query": "auth middleware"},
                        },
                    },
                ],
            }

        if self._step == 3:
            # Step 3: delegate file editing to a sub-agent
            return {
                "content": "Found the file. Let me delegate the edit to the file-ops sub-agent.",
                "tool_calls": [
                    {
                        "id": "call_3",
                        "function": {
                            "name": "file_ops_agent",
                            "arguments": {"task": "Add rate-limiting middleware to auth.py"},
                        },
                    },
                ],
            }

        if self._step == 4:
            # Step 4: run tests via test sub-agent
            return {
                "content": "Edit done. Now running tests to verify.",
                "tool_calls": [
                    {
                        "id": "call_4",
                        "function": {
                            "name": "test_agent",
                            "arguments": {"task": "Run auth middleware tests"},
                        },
                    },
                ],
            }

        if self._step == 5:
            # Step 5: store a learning in memory
            return {
                "content": "Tests passed. Let me remember this pattern for future.",
                "tool_calls": [
                    {
                        "id": "call_5",
                        "function": {
                            "name": "memory_store",
                            "arguments": {
                                "key": "rate_limit_pattern",
                                "value": "Applied rate-limiting as middleware decorator in auth.py",
                            },
                        },
                    },
                ],
            }

        # Final: synthesise answer
        return {
            "content": (
                "Done! I've added rate-limiting middleware to auth.py.\n"
                "Changes:\n"
                "  - Added RateLimitMiddleware class\n"
                "  - Applied it to /login and /register endpoints\n"
                "  - All 12 tests pass\n"
                "I've stored the rate-limiting pattern in memory for future reference."
            ),
            "tool_calls": [],
        }


class SubAgentProvider:
    """Generic sub-agent provider that uses one tool then responds."""

    def __init__(self, name):
        self.name = name
        self._call = 0

    async def complete(self, **kwargs):
        self._call += 1
        tools = kwargs.get("tools", [])

        if self._call == 1 and tools:
            return {
                "content": f"[{self.name}] Working on it...",
                "tool_calls": [
                    {
                        "id": f"sub_{self._call}",
                        "function": {
                            "name": tools[0]["function"]["name"],
                            "arguments": {"path": "src/auth.py"},
                        },
                    },
                ],
            }

        return {
            "content": f"[{self.name}] Completed successfully.",
            "tool_calls": [],
        }


# ============================================================================
# Tools — simulated filesystem, search, and test runner
# ============================================================================

def _make_file_tools():
    """Tools for file operations."""
    return [
        Tool(
            name="read_file",
            description="Read the contents of a file at the given path",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            execute=lambda path: f"Contents of {path}:\nclass AuthMiddleware:\n    pass\n",
        ),
        Tool(
            name="write_file",
            description="Write content to a file at the given path",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "default": ""},
                },
                "required": ["path"],
            },
            execute=lambda path, content="": f"Wrote {len(content)} chars to {path}",
        ),
        Tool(
            name="list_directory",
            description="List files in a directory",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            execute=lambda path: "auth.py  middleware.py  routes.py  tests/",
        ),
    ]


def _make_search_tools():
    """Tools for code search."""
    return [
        Tool(
            name="code_search",
            description="Search the codebase for symbols, patterns, or text using ripgrep",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=lambda query: (
                f"Search results for '{query}':\n"
                "  src/auth.py:12  class AuthMiddleware\n"
                "  src/auth.py:45  def verify_token\n"
                "  src/routes.py:8  @auth_required\n"
            ),
        ),
        Tool(
            name="find_references",
            description="Find all references to a symbol in the codebase",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=lambda query: f"References to '{query}': 3 files, 7 occurrences",
        ),
    ]


def _make_test_tools():
    """Tools for test execution."""
    return [
        Tool(
            name="run_tests",
            description="Run the test suite or specific test files",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
                "required": [],
            },
            execute=lambda path=".": "12 tests passed, 0 failed, 0 skipped",
        ),
        Tool(
            name="run_linter",
            description="Run code linting and formatting checks",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
                "required": [],
            },
            execute=lambda path=".": "Lint: 0 errors, 0 warnings",
        ),
    ]


def _make_shell_tools():
    """Tools for shell commands."""
    return [
        Tool(
            name="bash",
            description="Execute a bash command in the project directory",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            execute=lambda command: f"$ {command}\n(simulated output)",
        ),
        Tool(
            name="git_command",
            description="Execute a git command for version control",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            execute=lambda command: f"git {command}\n(simulated git output)",
        ),
    ]


# ============================================================================
# Build the agent
# ============================================================================

async def main():
    print("=" * 70)
    print("  Claude Code-Style Coding Agent (built with Water)")
    print("=" * 70)

    # --- 1. Set up layered memory --------------------------------------
    print("\n[Setup] Initialising layered memory...")
    memory = MemoryManager()

    # Pre-load org and project memories
    await memory.add(
        "code_style", "Use type hints everywhere. Prefer async/await.",
        MemoryLayer.ORG,
    )
    await memory.add(
        "project_stack", "Python 3.12, FastAPI, PostgreSQL, pytest",
        MemoryLayer.PROJECT,
    )
    await memory.add(
        "auth_notes", "Auth module was refactored last sprint. Use new middleware pattern.",
        MemoryLayer.PROJECT,
    )
    print(f"  Loaded {len(await memory.get_all())} memories across layers")

    memory_tools = create_memory_tools(memory)

    # --- 2. Set up all tools -------------------------------------------
    file_tools = _make_file_tools()
    search_tools = _make_search_tools()
    test_tools = _make_test_tools()
    shell_tools = _make_shell_tools()

    all_tools = file_tools + search_tools + test_tools + shell_tools + memory_tools
    print(f"[Setup] {len(all_tools)} tools available")

    # --- 3. Semantic tool selection ------------------------------------
    print("[Setup] Building semantic tool index...")
    selector = create_tool_selector(
        tools=all_tools,
        top_k=5,
        always_include=["memory_recall", "memory_store"],  # Always available
    )

    # Demo: show which tools get selected for different queries
    demo_queries = [
        "search for auth code",
        "write to a file",
        "run the tests",
    ]
    for q in demo_queries:
        selected = selector.select(q)
        print(f"  '{q}' -> {[t.name for t in selected]}")

    # --- 4. Create sub-agents ------------------------------------------
    print("\n[Setup] Creating sub-agents...")

    file_ops_agent = create_sub_agent_tool(SubAgentConfig(
        id="file_ops_agent",
        provider=SubAgentProvider("file-ops"),
        tools=file_tools,
        system_prompt="You are a file operations specialist. Read, write, and manage files.",
        max_iterations=3,
    ))

    test_agent = create_sub_agent_tool(SubAgentConfig(
        id="test_agent",
        provider=SubAgentProvider("tester"),
        tools=test_tools,
        system_prompt="You are a test runner. Execute tests and report results.",
        max_iterations=3,
    ))

    print(f"  Created: file_ops_agent, test_agent")

    # --- 5. Build the orchestrator agent --------------------------------
    # The orchestrator has access to: search tools, memory tools, and sub-agents
    orchestrator_tools = search_tools + memory_tools + [file_ops_agent, test_agent]

    # Step tracing
    step_log = []

    def on_step(iteration, step):
        think = step["think"][:80] if step["think"] else "(no thought)"
        actions = step.get("act") or []
        tool_names = [a["tool"] for a in actions] if actions else ["(none)"]
        step_log.append({"iteration": iteration, "thought": think, "tools": tool_names})
        print(f"  Step {iteration}: thought='{think}' tools={tool_names}")

    # Tool-call gating: block dangerous operations
    blocked_tools = {"bash", "git_command"}

    def on_tool_call(tool_name, tool_args):
        if tool_name in blocked_tools:
            print(f"  [GATE] Blocked tool: {tool_name}")
            return False
        return True

    print("\n[Running] Orchestrator agent processing request...")
    print("-" * 70)

    agent_task = create_agentic_task(
        id="claude-code-agent",
        provider=OrchestratorProvider(),
        tools=orchestrator_tools,
        tool_selector=create_tool_selector(
            tools=orchestrator_tools,
            top_k=4,
            always_include=["memory_recall", "memory_store"],
        ),
        system_prompt=(
            "You are an expert coding assistant. You can search code, delegate "
            "file edits to sub-agents, run tests, and manage memory of project "
            "knowledge. Always verify changes with tests before finishing.\n\n"
            + memory.to_system_prompt()
        ),
        max_iterations=10,
        on_step=on_step,
        on_tool_call=on_tool_call,
    )

    result = await agent_task.execute(
        {"input_data": {"prompt": "Add rate-limiting middleware to the auth module"}},
        None,
    )

    print("-" * 70)

    # --- 6. Print results -----------------------------------------------
    print(f"\n[Result] Final response:\n{result['response']}")
    print(f"\n[Result] Total iterations: {result['iterations']}")
    print(f"[Result] Tools used: {[h['tool'] for h in result['tool_history']]}")

    # --- 7. Verify memory was updated ----------------------------------
    print("\n[Memory] Checking updated memory...")
    learned = await memory.get_all(MemoryLayer.AUTO_LEARNED)
    for e in learned:
        print(f"  [{e.layer.value}] {e.key}: {e.value}")

    # --- 8. Show step trace --------------------------------------------
    print(f"\n[Trace] {len(step_log)} steps recorded:")
    for s in step_log:
        print(f"  #{s['iteration']}: {s['tools']}")

    print("\nAll examples passed!")


if __name__ == "__main__":
    asyncio.run(main())
