"""
Chat integration module for Water flows.

Connects Water flows to messaging platforms (Slack, Discord, Telegram)
via a pluggable adapter pattern. Includes an InMemoryAdapter for testing.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from water.core.flow import Flow

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Represents an incoming chat message."""

    text: str
    channel: str
    user: str
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChatAdapter(ABC):
    """Abstract base class for chat platform adapters."""

    @abstractmethod
    async def send_message(self, channel: str, text: str, **kwargs) -> None:
        """Send a message to a channel."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start listening for messages."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter."""
        ...


class InMemoryAdapter(ChatAdapter):
    """
    In-memory adapter for testing. Stores sent messages in a list
    and allows injecting messages to simulate incoming traffic.
    """

    def __init__(self) -> None:
        self.sent_messages: List[Dict[str, Any]] = []
        self._message_handler: Optional[Callable] = None
        self._running: bool = False

    async def send_message(self, channel: str, text: str, **kwargs) -> None:
        self.sent_messages.append({"channel": channel, "text": text, **kwargs})

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def set_message_handler(self, handler: Callable) -> None:
        """Set the callback invoked when a message is injected."""
        self._message_handler = handler

    async def inject_message(self, message: ChatMessage) -> Optional[str]:
        """Simulate an incoming message. Returns the handler's response."""
        if self._message_handler:
            return await self._message_handler(message)
        return None


class ChatBot:
    """
    Main bot that connects Water flows to a chat adapter.

    Register flows as chat commands via ``register_flow``, add custom
    handlers with the ``@on_message`` decorator, then call ``start``.
    """

    def __init__(self, adapter: ChatAdapter, flows: Optional[Dict[str, Flow]] = None):
        self.adapter = adapter
        self.flows: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable] = {}

        if flows:
            for trigger, flow in flows.items():
                self.register_flow(trigger, flow)

        # Wire up the adapter so injected messages reach handle_message
        if hasattr(adapter, "set_message_handler"):
            adapter.set_message_handler(self.handle_message)

    def register_flow(self, trigger: str, flow: Flow, description: str = "") -> None:
        """Register a flow to be triggered by a command/keyword."""
        self.flows[trigger] = {
            "flow": flow,
            "description": description or flow.description,
        }

    def on_message(self, pattern: str):
        """Decorator to register a custom message handler for a regex pattern."""

        def decorator(func: Callable):
            self._handlers[pattern] = func
            return func

        return decorator

    async def handle_message(self, message: ChatMessage) -> Optional[str]:
        """
        Process an incoming message.

        1. Check for the built-in ``help`` command.
        2. Check registered flow triggers.
        3. Check custom pattern handlers.
        4. Reply with an unknown-command message if nothing matches.
        """
        text = message.text.strip()

        # Built-in help command
        if text.lower() == "help":
            return await self._handle_help(message)

        # Check flow triggers
        for trigger, entry in self.flows.items():
            if text == trigger or text.startswith(trigger + " "):
                return await self._run_flow(trigger, entry, message)

        # Check custom pattern handlers
        for pattern, handler in self._handlers.items():
            if re.search(pattern, text):
                result = handler(message)
                if asyncio.iscoroutine(result):
                    result = await result
                if result is not None:
                    await self.adapter.send_message(message.channel, str(result))
                return result

        # Unknown command
        response = f"Unknown command: {text.split()[0] if text else text}. Type 'help' for available commands."
        await self.adapter.send_message(message.channel, response)
        return response

    async def _handle_help(self, message: ChatMessage) -> str:
        """Build and send a help response listing available commands."""
        lines = ["Available commands:"]
        for trigger, entry in self.flows.items():
            lines.append(f"  {trigger} - {entry['description']}")
        for pattern in self._handlers:
            lines.append(f"  /{pattern}/ (custom handler)")
        if not self.flows and not self._handlers:
            lines.append("  (no commands registered)")
        response = "\n".join(lines)
        await self.adapter.send_message(message.channel, response)
        return response

    async def _run_flow(
        self, trigger: str, entry: Dict[str, Any], message: ChatMessage
    ) -> Optional[str]:
        """Parse args from the message, run the flow, and send the result."""
        flow: Flow = entry["flow"]
        text = message.text.strip()

        # Extract arguments: everything after the trigger word
        args_text = text[len(trigger):].strip()
        input_data: Dict[str, Any] = {
            "text": args_text,
            "channel": message.channel,
            "user": message.user,
        }
        # Try to parse key=value pairs from the args
        if args_text:
            for part in args_text.split():
                if "=" in part:
                    key, _, value = part.partition("=")
                    input_data[key] = value

        try:
            result = await flow.run(input_data)
            response = str(result)
            await self.adapter.send_message(message.channel, response)
            return response
        except Exception as e:
            error_msg = f"Flow '{flow.id}' failed: {e}"
            await self.adapter.send_message(message.channel, error_msg)
            logger.error(error_msg, exc_info=True)
            return error_msg

    async def start(self) -> None:
        """Start listening for messages."""
        await self.adapter.start()

    async def stop(self) -> None:
        """Stop the bot."""
        await self.adapter.stop()


class FlowNotification:
    """Sends flow lifecycle notifications to a chat channel."""

    def __init__(self, adapter: ChatAdapter, channel: str) -> None:
        self.adapter = adapter
        self.channel = channel

    async def notify_start(self, flow_id: str, execution_id: str) -> None:
        text = f"Flow '{flow_id}' started (execution: {execution_id})"
        await self.adapter.send_message(self.channel, text)

    async def notify_complete(
        self, flow_id: str, execution_id: str, result: Any
    ) -> None:
        text = f"Flow '{flow_id}' completed (execution: {execution_id}). Result: {result}"
        await self.adapter.send_message(self.channel, text)

    async def notify_error(
        self, flow_id: str, execution_id: str, error: Any
    ) -> None:
        text = f"Flow '{flow_id}' failed (execution: {execution_id}). Error: {error}"
        await self.adapter.send_message(self.channel, text)


# ---------------------------------------------------------------------------
# Platform adapters (lazy imports)
# ---------------------------------------------------------------------------


class SlackAdapter(ChatAdapter):
    """
    Slack adapter using ``slack_sdk``.

    Sends messages via a webhook URL and receives them through socket mode.
    """

    def __init__(self, token: str, webhook_url: str = "", app_token: str = "") -> None:
        self.token = token
        self.webhook_url = webhook_url
        self.app_token = app_token
        self._client = None
        self._socket_client = None

    async def send_message(self, channel: str, text: str, **kwargs) -> None:
        try:
            from slack_sdk.web.async_client import AsyncWebClient
        except ImportError:
            raise ImportError(
                "slack_sdk is required for SlackAdapter. "
                "Install it with: pip install slack_sdk"
            )

        if self._client is None:
            self._client = AsyncWebClient(token=self.token)

        await self._client.chat_postMessage(channel=channel, text=text, **kwargs)

    async def start(self) -> None:
        try:
            from slack_sdk.socket_mode.aiohttp import SocketModeClient  # noqa: F401
        except ImportError:
            raise ImportError(
                "slack_sdk with socket mode support is required. "
                "Install it with: pip install slack_sdk[socket-mode]"
            )
        logger.info("SlackAdapter started")

    async def stop(self) -> None:
        if self._socket_client:
            await self._socket_client.close()
        logger.info("SlackAdapter stopped")


class DiscordAdapter(ChatAdapter):
    """
    Discord adapter using ``discord.py``.
    """

    def __init__(self, token: str) -> None:
        self.token = token
        self._client = None

    async def send_message(self, channel: str, text: str, **kwargs) -> None:
        try:
            import discord  # noqa: F401
        except ImportError:
            raise ImportError(
                "discord.py is required for DiscordAdapter. "
                "Install it with: pip install discord.py"
            )

        if self._client is None:
            raise RuntimeError("DiscordAdapter must be started before sending messages")

        ch = self._client.get_channel(int(channel))
        if ch:
            await ch.send(text, **kwargs)

    async def start(self) -> None:
        try:
            import discord  # noqa: F401
        except ImportError:
            raise ImportError(
                "discord.py is required for DiscordAdapter. "
                "Install it with: pip install discord.py"
            )
        logger.info("DiscordAdapter started")

    async def stop(self) -> None:
        if self._client:
            await self._client.close()
        logger.info("DiscordAdapter stopped")


class TelegramAdapter(ChatAdapter):
    """
    Telegram adapter using ``python-telegram-bot``.
    """

    def __init__(self, token: str) -> None:
        self.token = token
        self._app = None

    async def send_message(self, channel: str, text: str, **kwargs) -> None:
        try:
            from telegram import Bot  # noqa: F401
        except ImportError:
            raise ImportError(
                "python-telegram-bot is required for TelegramAdapter. "
                "Install it with: pip install python-telegram-bot"
            )

        if self._app is None:
            from telegram import Bot

            self._app = Bot(token=self.token)

        await self._app.send_message(chat_id=channel, text=text, **kwargs)

    async def start(self) -> None:
        try:
            from telegram.ext import ApplicationBuilder  # noqa: F401
        except ImportError:
            raise ImportError(
                "python-telegram-bot is required for TelegramAdapter. "
                "Install it with: pip install python-telegram-bot"
            )
        logger.info("TelegramAdapter started")

    async def stop(self) -> None:
        if self._app:
            await self._app.shutdown()
        logger.info("TelegramAdapter stopped")
