# Water

**A multi-agent orchestration framework that works with any agent framework.**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PyPI](https://img.shields.io/pypi/v/water-ai)](https://pypi.org/project/water-ai/)
[![Python](https://img.shields.io/pypi/pyversions/water-ai)](https://pypi.org/project/water-ai/)

## Overview

Water is a production-ready orchestration framework for building complex multi-agent systems without being locked into a specific agent framework. Whether you use LangChain, CrewAI, Agno, or custom agents, Water provides the orchestration layer to coordinate and scale your workflows.

## Installation

```bash
pip install water-ai
```

## Quick Start

```python
import asyncio
from water import Flow, create_task
from pydantic import BaseModel

class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    result: int

def add_five(params, context):
    return {"result": params["input_data"]["value"] + 5}

task = create_task(
    id="add",
    description="Add five",
    input_schema=NumberInput,
    output_schema=NumberOutput,
    execute=add_five,
)

flow = Flow(id="math", description="Math flow").then(task).register()

async def main():
    result = await flow.run({"value": 10})
    print(result)  # {"result": 15}

asyncio.run(main())
```

## Flow Patterns

Water supports composable flow patterns that chain together with a fluent API:

```python
flow = Flow(id="pipeline", description="Example pipeline")

# Sequential — tasks run one after another
flow.then(task_a).then(task_b).then(task_c)

# Parallel — tasks run concurrently, results are merged
flow.parallel([task_a, task_b, task_c])

# Conditional branching — route to different tasks based on data
flow.branch([
    (lambda data: data["type"] == "email", email_task),
    (lambda data: data["type"] == "sms", sms_task),
])

# Loop — repeat a task while a condition holds
flow.loop(lambda data: data["retries"] < 3, retry_task, max_iterations=5)

# Map — run a task for each item in a list (parallel)
flow.map(process_task, over="items")

# DAG — define tasks with explicit dependencies
flow.dag(
    [task_a, task_b, task_c],
    dependencies={"task_c": ["task_a", "task_b"]},
)

# Subflow — compose flows into tasks
flow.then(inner_flow.as_task())

# Conditional execution & fallbacks
flow.then(task, when=lambda data: data["enabled"])
flow.then(task, fallback=fallback_task)
```

## Agent Harness

Water provides infrastructure around your AI agents — not the agents themselves.

### LLM Tasks

Use any LLM provider through a unified interface:

```python
from water.agents import create_agent_task, OpenAIProvider, AnthropicProvider

agent = create_agent_task(
    id="writer",
    description="Write copy",
    provider=OpenAIProvider(model="gpt-4o"),
    system_prompt="You are a copywriter.",
)
```

### Multi-Agent Orchestration

Coordinate multiple agents with shared context:

```python
from water.agents import create_agent_team, AgentRole

team = create_agent_team(
    team_id="research",
    roles=[
        AgentRole(id="researcher", provider=provider, system_prompt="Research the topic."),
        AgentRole(id="writer", provider=provider, system_prompt="Write the article."),
    ],
    strategy="sequential",  # or "round_robin", "dynamic"
)
```

### Approval Gates

Add human approval checkpoints for high-risk operations:

```python
from water.agents import create_approval_task, ApprovalPolicy, RiskLevel

approval = create_approval_task(
    id="deploy_check",
    policy=ApprovalPolicy(
        required_for=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        auto_approve=[RiskLevel.LOW],
        timeout_seconds=300,
    ),
)
```

### Sandboxed Execution

Run untrusted code in isolated environments:

```python
from water.agents import create_sandboxed_task, SandboxConfig

sandboxed = create_sandboxed_task(
    id="run_code",
    config=SandboxConfig(timeout=30, max_memory_mb=512),
    backend="subprocess",  # or "docker", "memory"
)
```

## Resilience

Built-in patterns for production reliability:

```python
from water.resilience import CircuitBreaker, RateLimiter, InMemoryCheckpoint

# Circuit breaker — stop calling failing services
cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

# Rate limiter — control throughput
limiter = RateLimiter(max_calls=100, period=60)

# Checkpoint — resume flows after crashes
flow.checkpoint = InMemoryCheckpoint()

# Dead-letter queue — capture failed tasks for inspection
from water.resilience import InMemoryDLQ
flow.dlq = InMemoryDLQ()
```

Tasks also support retry and timeout out of the box:

```python
task = create_task(
    id="flaky",
    description="Flaky API call",
    execute=call_api,
    retry_count=3,
    retry_delay=1.0,
    retry_backoff=2.0,
    timeout=30.0,
)
```

## Integrations

### MCP (Model Context Protocol)

Expose flows as MCP tools or call external MCP servers:

```python
from water.integrations import MCPServer, MCPClient

# Serve flows as MCP tools
server = MCPServer(flows=[my_flow])

# Call external MCP tools from a task
client = MCPClient(server_url="http://localhost:3000")
mcp_task = create_mcp_task(id="search", client=client, tool_name="web_search")
```

### Chat Adapters

Connect flows to Slack, Discord, or Telegram:

```python
from water.integrations import ChatBot, SlackAdapter

bot = ChatBot(adapter=SlackAdapter(token="xoxb-..."), flows=[support_flow])
```

### SSE Streaming

Stream flow execution events in real time:

```python
from water.integrations import StreamingFlow

streaming = StreamingFlow(flow)
# Subscribe to events via SSE at /flows/{id}/stream
```

## Server

Serve your flows as a REST API with one line:

```python
from water.server import FlowServer

server = FlowServer(flows=[flow_a, flow_b])
app = server.get_app()

# Routes:
# GET  /flows              — list all flows
# GET  /flows/{id}         — flow details
# POST /flows/{id}/run     — execute a flow
# GET  /health             — health check
# GET  /dashboard          — observability UI
```

```bash
uvicorn app:app --reload
```

## CLI

```bash
# Run a flow
water run cookbook.sequential_flow:registration_flow --input '{"email": "a@b.com", "password": "secret", "first_name": "Water"}'

# Visualize as Mermaid diagram
water visualize cookbook.sequential_flow:registration_flow

# Validate without executing
water dry-run cookbook.sequential_flow:registration_flow --input '{"email": "a@b.com"}'

# List all flows in a module
water list cookbook.sequential_flow

# Deploy to Render
water flow prod:render --app playground
```

## Observability

```python
from water.observability import TelemetryManager, FlowDashboard

# OpenTelemetry integration
telemetry = TelemetryManager(service_name="my-service")

# Built-in dashboard (served at /dashboard)
dashboard = FlowDashboard(storage=my_storage)
```

## Architecture

```
water/
├── core/           # Flow, Task, ExecutionEngine, Context
├── agents/         # LLM tasks, multi-agent, approval, sandbox
├── storage/        # InMemory, SQLite, Redis, Postgres backends
├── resilience/     # Circuit breaker, rate limiter, cache, checkpoint, DLQ
├── middleware/     # Middleware, hooks, events
├── integrations/   # MCP, chat adapters, SSE streaming
├── observability/  # Telemetry, dashboard
├── server/         # FlowServer (FastAPI)
└── utils/          # Testing, scheduler, declarative loader, secrets, CLI
```

## Cookbook

The [`cookbook/`](cookbook/) directory has 47 runnable examples covering every feature:

| Example | What it shows |
|---------|---------------|
| [`sequential_flow.py`](cookbook/sequential_flow.py) | Basic `.then()` chaining |
| [`parallel_flow.py`](cookbook/parallel_flow.py) | Concurrent task execution |
| [`branched_flow.py`](cookbook/branched_flow.py) | Conditional routing |
| [`dag_flow.py`](cookbook/dag_flow.py) | Dependency graphs |
| [`agent_task_flow.py`](cookbook/agent_task_flow.py) | LLM-powered tasks |
| [`multi_agent_flow.py`](cookbook/multi_agent_flow.py) | Agent team coordination |
| [`approval_flow.py`](cookbook/approval_flow.py) | Human approval gates |
| [`sandbox_flow.py`](cookbook/sandbox_flow.py) | Sandboxed code execution |
| [`mcp_flow.py`](cookbook/mcp_flow.py) | MCP tool interop |
| [`streaming_flow.py`](cookbook/streaming_flow.py) | Real-time SSE events |
| [`checkpoint_flow.py`](cookbook/checkpoint_flow.py) | Crash recovery |
| [`playground.py`](cookbook/playground.py) | Multi-flow REST server |

## Contributing

We welcome contributions — bug reports, feature requests, code, docs, and testing.

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
