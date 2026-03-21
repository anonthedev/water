"""Webhook trigger for HTTP-based event-driven flow execution."""

import hashlib
import hmac
from typing import Any, Dict, Optional, Callable

from water.triggers.base import Trigger, TriggerEvent


class WebhookTrigger(Trigger):
    """Trigger that fires when an HTTP webhook request is received.

    The trigger registers a path on the FlowServer and optionally
    verifies HMAC-SHA256 signatures for security.

    Args:
        flow_name: The ID of the flow to execute.
        path: URL path for the webhook endpoint (default ``/webhook``).
        secret: Optional shared secret for HMAC-SHA256 signature verification.
        transform: Optional callable to transform the incoming payload.
        methods: HTTP methods to accept (default ``["POST"]``).

    Example::

        trigger = WebhookTrigger(
            flow_name="process-order",
            path="/hooks/orders",
            secret="my-secret-key",
        )
    """

    def __init__(
        self,
        flow_name: str,
        path: str = "/webhook",
        secret: Optional[str] = None,
        transform: Optional[Callable] = None,
        methods: Optional[list] = None,
    ) -> None:
        super().__init__(flow_name, transform)
        self.path = path
        self.secret = secret
        self.methods = methods or ["POST"]
        self._received_events: list = []

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify an HMAC-SHA256 signature against the request body.

        Args:
            body: Raw request body bytes.
            signature: The signature string to verify (hex digest).

        Returns:
            ``True`` if the signature is valid or no secret is configured,
            ``False`` otherwise.
        """
        if not self.secret:
            return True
        expected = hmac.new(
            self.secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_request(self, payload: Dict[str, Any], signature: Optional[str] = None, raw_body: Optional[bytes] = None) -> TriggerEvent:
        """Process an incoming webhook request.

        Args:
            payload: Parsed JSON payload from the request.
            signature: Optional signature header value.
            raw_body: Raw request body bytes for signature verification.

        Returns:
            A TriggerEvent representing this webhook invocation.

        Raises:
            ValueError: If signature verification fails.
        """
        if self.secret and signature:
            body = raw_body or b""
            if not self.verify_signature(body, signature):
                raise ValueError("Invalid webhook signature")

        event = self.create_event(payload, path=self.path)
        self._received_events.append(event)
        return event

    async def start(self) -> None:
        """Activate the webhook trigger."""
        self._active = True

    async def stop(self) -> None:
        """Deactivate the webhook trigger."""
        self._active = False
