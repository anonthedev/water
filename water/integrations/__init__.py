from water.integrations.mcp import MCPServer, MCPClient, create_mcp_task
from water.integrations.chat import (
    ChatAdapter,
    ChatBot,
    ChatMessage,
    FlowNotification,
    InMemoryAdapter,
    SlackAdapter,
    DiscordAdapter,
    TelegramAdapter,
)
from water.integrations.streaming import (
    StreamEvent,
    StreamManager,
    StreamingFlow,
    add_streaming_routes,
)
from water.integrations.a2a import (
    A2AServer,
    A2AClient,
    A2ATask,
    A2AMessage,
    AgentCard,
    AgentSkill,
    MessagePart,
    TaskState as A2ATaskState,
    create_a2a_task,
)
