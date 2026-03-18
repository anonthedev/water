"""
Chat Flow Cookbook Example

Demonstrates how to connect Water flows to messaging platforms using the
chat integration module. This example uses the InMemoryAdapter so it runs
without any external services.

For real deployments, swap InMemoryAdapter with SlackAdapter, DiscordAdapter,
or TelegramAdapter (see commented-out examples at the bottom).
"""

import asyncio
from pydantic import BaseModel

from water.core import Flow, create_task
from water.integrations.chat import (
    ChatBot,
    ChatMessage,
    FlowNotification,
    InMemoryAdapter,
)


# ---------------------------------------------------------------------------
# 1. Define schemas and tasks
# ---------------------------------------------------------------------------

class GreetInput(BaseModel):
    text: str
    channel: str = ""
    user: str = ""
    name: str = ""


class GreetOutput(BaseModel):
    result: str


async def greet_execute(params, context):
    name = params["input_data"].get("name") or params["input_data"].get("text", "World")
    return {"result": f"Hello, {name}!"}


greet_task = create_task(
    id="greet_task",
    description="Greet a user by name",
    input_schema=GreetInput,
    output_schema=GreetOutput,
    execute=greet_execute,
)


class StatusInput(BaseModel):
    text: str
    channel: str = ""
    user: str = ""


class StatusOutput(BaseModel):
    result: str


status_task = create_task(
    id="status_task",
    description="Return system status",
    input_schema=StatusInput,
    output_schema=StatusOutput,
    execute=lambda params, ctx: {"result": "All systems operational."},
)


# ---------------------------------------------------------------------------
# 2. Build and register flows
# ---------------------------------------------------------------------------

greet_flow = Flow(id="greet_flow", description="Greet someone by name")
greet_flow.then(greet_task).register()

status_flow = Flow(id="status_flow", description="Check system status")
status_flow.then(status_task).register()


# ---------------------------------------------------------------------------
# 3. Set up the ChatBot with InMemoryAdapter
# ---------------------------------------------------------------------------

async def main():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)

    # Register flows as chat commands
    bot.register_flow("greet", greet_flow, description="Greet someone (usage: greet <name>)")
    bot.register_flow("status", status_flow, description="Check system status")

    # Custom handler using the @on_message decorator
    @bot.on_message(r"^ping$")
    async def handle_ping(message: ChatMessage):
        return "pong"

    await bot.start()

    # --- Simulate conversations ---

    print("=== ChatBot Demo ===\n")

    # Ask for help
    msg = ChatMessage(text="help", channel="#general", user="alice")
    result = await adapter.inject_message(msg)
    print(f"[help]\n{result}\n")

    # Trigger the greet flow
    msg = ChatMessage(text="greet name=Alice", channel="#general", user="bob")
    result = await adapter.inject_message(msg)
    print(f"[greet name=Alice] -> {result}\n")

    # Trigger the status flow
    msg = ChatMessage(text="status", channel="#ops", user="carol")
    result = await adapter.inject_message(msg)
    print(f"[status] -> {result}\n")

    # Custom handler
    msg = ChatMessage(text="ping", channel="#general", user="dave")
    result = await adapter.inject_message(msg)
    print(f"[ping] -> {result}\n")

    # Unknown command
    msg = ChatMessage(text="deploy", channel="#general", user="eve")
    result = await adapter.inject_message(msg)
    print(f"[deploy] -> {result}\n")

    # --- Flow notifications ---

    print("=== Flow Notifications ===\n")

    notifier = FlowNotification(adapter=adapter, channel="#alerts")
    await notifier.notify_start("data_pipeline", "exec-001")
    await notifier.notify_complete("data_pipeline", "exec-001", {"rows": 1500})
    await notifier.notify_error("data_pipeline", "exec-002", "Connection timeout")

    for msg_record in adapter.sent_messages[-3:]:
        print(f"  [{msg_record['channel']}] {msg_record['text']}")

    await bot.stop()
    print("\nDone.")


# ---------------------------------------------------------------------------
# Platform adapter examples (commented out — require real tokens)
# ---------------------------------------------------------------------------

# --- Slack ---
# from water.integrations.chat import SlackAdapter
#
# slack_adapter = SlackAdapter(
#     token="xoxb-your-slack-bot-token",
#     app_token="xapp-your-slack-app-token",
#     webhook_url="https://hooks.slack.com/services/...",
# )
# bot = ChatBot(adapter=slack_adapter)
# bot.register_flow("deploy", deploy_flow, description="Trigger a deployment")

# --- Discord ---
# from water.integrations.chat import DiscordAdapter
#
# discord_adapter = DiscordAdapter(token="your-discord-bot-token")
# bot = ChatBot(adapter=discord_adapter)
# bot.register_flow("status", status_flow, description="Check system status")

# --- Telegram ---
# from water.integrations.chat import TelegramAdapter
#
# telegram_adapter = TelegramAdapter(token="your-telegram-bot-token")
# bot = ChatBot(adapter=telegram_adapter)
# bot.register_flow("greet", greet_flow, description="Greet a user")


if __name__ == "__main__":
    asyncio.run(main())
