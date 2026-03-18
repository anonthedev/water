# ---------------------------------------------------------------------------
# water — The production-ready agent harness framework for Python
# ---------------------------------------------------------------------------
# Subpackage layout:
#   water.core          – Flow, Task, ExecutionEngine, Context
#   water.storage       – StorageBackend, InMemory, SQLite, Redis, Postgres
#   water.resilience    – CircuitBreaker, RateLimiter, Cache, Checkpoint, DLQ
#   water.middleware     – Middleware, Hooks, Events
#   water.agents        – LLM tasks, Multi-agent, Approval, Human, Sandbox
#   water.integrations  – MCP, Chat, Streaming
#   water.observability – Telemetry, Dashboard
#   water.server        – FlowServer (FastAPI)
#   water.utils         – Testing, Scheduler, Declarative, Secrets, CLI
# ---------------------------------------------------------------------------

# --- Core ---
from water.core import Flow, Task, create_task, ExecutionContext
from water.core.engine import FlowPausedError, FlowStoppedError

# --- Storage ---
from water.storage import (
    StorageBackend,
    InMemoryStorage,
    SQLiteStorage,
    FlowSession,
    FlowStatus,
    TaskRun,
    RedisStorage,
    PostgresStorage,
)

# --- Resilience ---
from water.resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    RateLimiter,
    get_rate_limiter,
    TaskCache,
    InMemoryCache,
    CheckpointBackend,
    InMemoryCheckpoint,
    DeadLetter,
    DeadLetterQueue,
    InMemoryDLQ,
)

# --- Middleware & Lifecycle ---
from water.middleware import (
    Middleware,
    LoggingMiddleware,
    TransformMiddleware,
    HookManager,
    EventEmitter,
    FlowEvent,
    EventSubscription,
)

# --- Agents ---
from water.agents import (
    create_agent_task,
    LLMProvider,
    MockProvider,
    OpenAIProvider,
    AnthropicProvider,
    CustomProvider,
    AgentInput,
    AgentOutput,
    AgentRole,
    SharedContext,
    AgentOrchestrator,
    create_agent_team,
    RiskLevel,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalGate,
    ApprovalDenied,
    create_approval_task,
    create_human_task,
    HumanInputManager,
    HumanInputRequired,
    SandboxConfig,
    SandboxResult,
    SandboxBackend,
    InMemorySandbox,
    SubprocessSandbox,
    DockerSandbox,
    create_sandboxed_task,
)

# --- Integrations ---
from water.integrations import (
    MCPServer,
    MCPClient,
    create_mcp_task,
    ChatAdapter,
    ChatBot,
    ChatMessage,
    FlowNotification,
    InMemoryAdapter,
    SlackAdapter,
    DiscordAdapter,
    TelegramAdapter,
    StreamEvent,
    StreamManager,
    StreamingFlow,
    add_streaming_routes,
)

# --- Observability ---
from water.observability import FlowDashboard, TelemetryManager, is_otel_available

# --- Server ---
from water.server import FlowServer

# --- Utils ---
from water.utils import (
    MockTask,
    FlowTestRunner,
    FlowScheduler,
    ScheduledJob,
    load_flow_from_dict,
    load_flow_from_yaml,
    load_flow_from_json,
    SecretValue,
    SecretsManager,
    EnvSecretsManager,
)

__all__ = [
    # Core
    "Flow",
    "Task",
    "create_task",
    "ExecutionContext",
    "FlowPausedError",
    "FlowStoppedError",
    # Storage
    "StorageBackend",
    "InMemoryStorage",
    "SQLiteStorage",
    "FlowSession",
    "FlowStatus",
    "TaskRun",
    "RedisStorage",
    "PostgresStorage",
    # Resilience
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "RateLimiter",
    "get_rate_limiter",
    "TaskCache",
    "InMemoryCache",
    "CheckpointBackend",
    "InMemoryCheckpoint",
    "DeadLetter",
    "DeadLetterQueue",
    "InMemoryDLQ",
    # Middleware & Lifecycle
    "Middleware",
    "LoggingMiddleware",
    "TransformMiddleware",
    "HookManager",
    "EventEmitter",
    "FlowEvent",
    "EventSubscription",
    # Agents
    "create_agent_task",
    "LLMProvider",
    "MockProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "CustomProvider",
    "AgentInput",
    "AgentOutput",
    "AgentRole",
    "SharedContext",
    "AgentOrchestrator",
    "create_agent_team",
    "RiskLevel",
    "ApprovalPolicy",
    "ApprovalRequest",
    "ApprovalGate",
    "ApprovalDenied",
    "create_approval_task",
    "create_human_task",
    "HumanInputManager",
    "HumanInputRequired",
    "SandboxConfig",
    "SandboxResult",
    "SandboxBackend",
    "InMemorySandbox",
    "SubprocessSandbox",
    "DockerSandbox",
    "create_sandboxed_task",
    # Integrations
    "MCPServer",
    "MCPClient",
    "create_mcp_task",
    "ChatAdapter",
    "ChatBot",
    "ChatMessage",
    "FlowNotification",
    "InMemoryAdapter",
    "SlackAdapter",
    "DiscordAdapter",
    "TelegramAdapter",
    "StreamEvent",
    "StreamManager",
    "StreamingFlow",
    "add_streaming_routes",
    # Observability
    "FlowDashboard",
    "TelemetryManager",
    "is_otel_available",
    # Server
    "FlowServer",
    # Utils
    "MockTask",
    "FlowTestRunner",
    "FlowScheduler",
    "ScheduledJob",
    "load_flow_from_dict",
    "load_flow_from_yaml",
    "load_flow_from_json",
    "SecretValue",
    "SecretsManager",
    "EnvSecretsManager",
]
