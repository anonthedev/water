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
