"""Tests for water.triggers -- webhook, cron, queue triggers and registry."""

import asyncio
import hashlib
import hmac
from datetime import datetime

import pytest

from water.triggers import (
    CronTrigger,
    QueueTrigger,
    TriggerEvent,
    TriggerRegistry,
    WebhookTrigger,
)


# ---------------------------------------------------------------------------
# TriggerEvent
# ---------------------------------------------------------------------------

class TestTriggerEvent:
    def test_creation_with_defaults(self):
        event = TriggerEvent(source="webhook", timestamp="2026-01-01T00:00:00", payload={"key": "val"})
        assert event.source == "webhook"
        assert event.payload == {"key": "val"}
        assert event.trigger_id  # auto-generated
        assert event.metadata == {}

    def test_creation_with_explicit_id(self):
        event = TriggerEvent(
            source="cron",
            timestamp="2026-01-01T00:00:00",
            payload={},
            trigger_id="custom-id",
            metadata={"extra": True},
        )
        assert event.trigger_id == "custom-id"
        assert event.metadata == {"extra": True}


# ---------------------------------------------------------------------------
# WebhookTrigger
# ---------------------------------------------------------------------------

class TestWebhookTrigger:
    def test_creation_and_path(self):
        trigger = WebhookTrigger(flow_name="my-flow", path="/hooks/github")
        assert trigger.flow_name == "my-flow"
        assert trigger.path == "/hooks/github"
        assert trigger.secret is None
        assert not trigger.active

    def test_default_path(self):
        trigger = WebhookTrigger(flow_name="f")
        assert trigger.path == "/webhook"

    def test_signature_verification_valid(self):
        secret = "test-secret"
        body = b'{"event":"push"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        trigger = WebhookTrigger(flow_name="f", secret=secret)
        assert trigger.verify_signature(body, sig) is True

    def test_signature_verification_invalid(self):
        trigger = WebhookTrigger(flow_name="f", secret="real-secret")
        assert trigger.verify_signature(b"body", "bad-signature") is False

    def test_signature_verification_no_secret(self):
        trigger = WebhookTrigger(flow_name="f")
        # No secret configured -- always passes
        assert trigger.verify_signature(b"anything", "anything") is True

    @pytest.mark.asyncio
    async def test_handle_request(self):
        trigger = WebhookTrigger(flow_name="f", path="/hook")
        await trigger.start()
        event = await trigger.handle_request({"action": "created"})
        assert event.payload == {"action": "created"}
        assert event.source == "WebhookTrigger"
        assert len(trigger._received_events) == 1
        await trigger.stop()


# ---------------------------------------------------------------------------
# CronTrigger
# ---------------------------------------------------------------------------

class TestCronTrigger:
    def test_parse_schedule_every_minute(self):
        trigger = CronTrigger(flow_name="f", schedule="* * * * *")
        parsed = trigger.parse_schedule()
        assert parsed["minute"] == list(range(0, 60))
        assert parsed["hour"] == list(range(0, 24))

    def test_parse_schedule_specific(self):
        trigger = CronTrigger(flow_name="f", schedule="30 9 * * 1")
        parsed = trigger.parse_schedule()
        assert parsed["minute"] == [30]
        assert parsed["hour"] == [9]
        assert parsed["weekday"] == [1]

    def test_parse_schedule_step(self):
        trigger = CronTrigger(flow_name="f", schedule="*/15 * * * *")
        parsed = trigger.parse_schedule()
        assert parsed["minute"] == [0, 15, 30, 45]

    def test_parse_schedule_range(self):
        trigger = CronTrigger(flow_name="f", schedule="0 9-17 * * *")
        parsed = trigger.parse_schedule()
        assert parsed["hour"] == list(range(9, 18))

    def test_parse_schedule_comma(self):
        trigger = CronTrigger(flow_name="f", schedule="0 9 * * 1,3,5")
        parsed = trigger.parse_schedule()
        assert parsed["weekday"] == [1, 3, 5]

    def test_parse_schedule_invalid(self):
        trigger = CronTrigger(flow_name="f", schedule="* *")
        with pytest.raises(ValueError, match="5 fields"):
            trigger.parse_schedule()

    def test_should_run_match(self):
        # Monday 2026-03-16 09:30
        dt = datetime(2026, 3, 16, 9, 30)
        trigger = CronTrigger(flow_name="f", schedule="30 9 * * 0")
        assert trigger.should_run(dt) is True  # weekday 0 = Monday in datetime

    def test_should_run_no_match(self):
        dt = datetime(2026, 3, 16, 10, 0)  # 10:00, not 9:30
        trigger = CronTrigger(flow_name="f", schedule="30 9 * * *")
        assert trigger.should_run(dt) is False


# ---------------------------------------------------------------------------
# QueueTrigger
# ---------------------------------------------------------------------------

class TestQueueTrigger:
    @pytest.mark.asyncio
    async def test_push_and_pop(self):
        trigger = QueueTrigger(flow_name="f")
        await trigger.start()
        await trigger.push({"msg": "hello"})
        assert trigger.pending == 1

        event = await trigger.pop()
        assert event.payload == {"msg": "hello"}
        assert trigger.pending == 0
        await trigger.stop()

    @pytest.mark.asyncio
    async def test_pop_nowait_empty(self):
        trigger = QueueTrigger(flow_name="f")
        await trigger.start()
        result = await trigger.pop_nowait()
        assert result is None
        await trigger.stop()

    @pytest.mark.asyncio
    async def test_push_when_inactive_raises(self):
        trigger = QueueTrigger(flow_name="f")
        with pytest.raises(RuntimeError, match="not active"):
            await trigger.push({"msg": "fail"})


# ---------------------------------------------------------------------------
# Transform payload
# ---------------------------------------------------------------------------

class TestTransformPayload:
    def test_transform_applied(self):
        trigger = WebhookTrigger(
            flow_name="f",
            transform=lambda p: {"wrapped": p},
        )
        result = trigger.transform_payload({"x": 1})
        assert result == {"wrapped": {"x": 1}}

    def test_no_transform(self):
        trigger = WebhookTrigger(flow_name="f")
        result = trigger.transform_payload({"x": 1})
        assert result == {"x": 1}


# ---------------------------------------------------------------------------
# Start / Stop lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_webhook_start_stop(self):
        trigger = WebhookTrigger(flow_name="f")
        assert not trigger.active
        await trigger.start()
        assert trigger.active
        await trigger.stop()
        assert not trigger.active

    @pytest.mark.asyncio
    async def test_cron_start_stop(self):
        trigger = CronTrigger(flow_name="f", schedule="* * * * *")
        await trigger.start()
        assert trigger.active
        await trigger.stop()
        assert not trigger.active

    @pytest.mark.asyncio
    async def test_queue_start_stop(self):
        trigger = QueueTrigger(flow_name="f")
        await trigger.start()
        assert trigger.active
        await trigger.stop()
        assert not trigger.active


# ---------------------------------------------------------------------------
# TriggerRegistry
# ---------------------------------------------------------------------------

class TestTriggerRegistry:
    def test_add_and_list(self):
        registry = TriggerRegistry()
        t1 = WebhookTrigger(flow_name="a")
        t2 = CronTrigger(flow_name="b")
        registry.add(t1)
        registry.add(t2)
        assert registry.count == 2
        assert registry.list_all() == [t1, t2]

    def test_remove(self):
        registry = TriggerRegistry()
        registry.add(WebhookTrigger(flow_name="a"))
        registry.add(CronTrigger(flow_name="a"))
        registry.add(QueueTrigger(flow_name="b"))
        registry.remove("a")
        assert registry.count == 1
        assert registry.list_all()[0].flow_name == "b"

    def test_get_triggers(self):
        registry = TriggerRegistry()
        t1 = WebhookTrigger(flow_name="x")
        t2 = CronTrigger(flow_name="x")
        t3 = QueueTrigger(flow_name="y")
        registry.add(t1)
        registry.add(t2)
        registry.add(t3)
        assert registry.get_triggers("x") == [t1, t2]
        assert registry.get_triggers("y") == [t3]
        assert registry.get_triggers("z") == []

    @pytest.mark.asyncio
    async def test_start_all_stop_all(self):
        registry = TriggerRegistry()
        t1 = WebhookTrigger(flow_name="a")
        t2 = CronTrigger(flow_name="b")
        t3 = QueueTrigger(flow_name="c")
        registry.add(t1)
        registry.add(t2)
        registry.add(t3)

        await registry.start_all()
        assert all(t.active for t in registry.list_all())

        await registry.stop_all()
        assert all(not t.active for t in registry.list_all())
