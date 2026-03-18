import pytest
import asyncio
from pydantic import BaseModel
from water.approval import (
    RiskLevel,
    ApprovalPolicy,
    ApprovalGate,
    ApprovalDenied,
    create_approval_task,
)
from water.flow import Flow


class SimpleInput(BaseModel):
    value: int


class SimpleOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_auto_approve_low_risk():
    """LOW risk is auto-approved with the default policy (auto_approve_below=LOW)."""
    gate = ApprovalGate()  # default policy: auto_approve_below=LOW

    task = create_approval_task(
        id="low_risk",
        action_description="Low risk action",
        risk_level=RiskLevel.LOW,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )

    flow = Flow(id="auto_approve", description="Auto approve flow")
    flow.then(task).register()

    result = await flow.run({"value": 42})
    assert result["value"] == 42

    # Verify it was auto-approved
    history = gate.get_history()
    assert len(history) == 1
    assert history[0].status == "approved"
    assert history[0].decided_by == "auto"


@pytest.mark.asyncio
async def test_require_approval_high_risk():
    """HIGH risk waits for manual approval."""
    gate = ApprovalGate()

    task = create_approval_task(
        id="high_risk",
        action_description="Deploy to production",
        risk_level=RiskLevel.HIGH,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )

    flow = Flow(id="manual_approve", description="Manual approve flow")
    flow.then(task).register()

    async def approve_later():
        for _ in range(100):
            pending = gate.get_pending()
            if pending:
                gate.approve(pending[0].request_id, decided_by="admin")
                return
            await asyncio.sleep(0.01)

    approver = asyncio.create_task(approve_later())
    result = await flow.run({"value": 99})
    await approver

    assert result["value"] == 99
    history = gate.get_history()
    assert len(history) == 1
    assert history[0].status == "approved"
    assert history[0].decided_by == "human:admin"


@pytest.mark.asyncio
async def test_deny_request():
    """Denied request raises ApprovalDenied."""
    gate = ApprovalGate()

    task = create_approval_task(
        id="deny_me",
        action_description="Dangerous action",
        risk_level=RiskLevel.HIGH,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )

    flow = Flow(id="deny_flow", description="Deny flow")
    flow.then(task).register()

    async def deny_later():
        for _ in range(100):
            pending = gate.get_pending()
            if pending:
                gate.deny(pending[0].request_id, reason="Too risky", decided_by="security")
                return
            await asyncio.sleep(0.01)

    denier = asyncio.create_task(deny_later())

    with pytest.raises(ApprovalDenied, match="denied"):
        await flow.run({"value": 1})
    await denier

    history = gate.get_history()
    assert len(history) == 1
    assert history[0].status == "denied"
    assert history[0].reason == "Too risky"


@pytest.mark.asyncio
async def test_timeout_deny():
    """Timeout with 'deny' policy raises ApprovalDenied."""
    policy = ApprovalPolicy(timeout=0.05, timeout_action="deny")
    gate = ApprovalGate(policy=policy)

    task = create_approval_task(
        id="timeout_deny",
        action_description="Will timeout",
        risk_level=RiskLevel.MEDIUM,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )

    flow = Flow(id="timeout_deny_flow", description="Timeout deny")
    flow.then(task).register()

    with pytest.raises(ApprovalDenied, match="Timed out"):
        await flow.run({"value": 1})

    history = gate.get_history()
    assert len(history) == 1
    assert history[0].status == "timed_out"
    assert history[0].decided_by == "timeout"


@pytest.mark.asyncio
async def test_timeout_approve():
    """Timeout with 'approve' policy auto-approves."""
    policy = ApprovalPolicy(timeout=0.05, timeout_action="approve")
    gate = ApprovalGate(policy=policy)

    task = create_approval_task(
        id="timeout_approve",
        action_description="Will auto-approve on timeout",
        risk_level=RiskLevel.MEDIUM,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )

    flow = Flow(id="timeout_approve_flow", description="Timeout approve")
    flow.then(task).register()

    result = await flow.run({"value": 77})
    assert result["value"] == 77

    history = gate.get_history()
    assert len(history) == 1
    assert history[0].status == "approved"
    assert history[0].decided_by == "timeout"


@pytest.mark.asyncio
async def test_approval_history():
    """History tracks all requests including auto-approved and manually resolved."""
    policy = ApprovalPolicy(auto_approve_below=RiskLevel.LOW, timeout=0.5)
    gate = ApprovalGate(policy=policy)

    # First: auto-approved low-risk
    task1 = create_approval_task(
        id="history_low",
        risk_level=RiskLevel.LOW,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )

    flow1 = Flow(id="h1", description="History 1")
    flow1.then(task1).register()
    await flow1.run({"value": 1})

    # Second: manually approved high-risk
    task2 = create_approval_task(
        id="history_high",
        risk_level=RiskLevel.HIGH,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )

    flow2 = Flow(id="h2", description="History 2")
    flow2.then(task2).register()

    async def approve_later():
        for _ in range(100):
            pending = gate.get_pending()
            if pending:
                gate.approve(pending[0].request_id)
                return
            await asyncio.sleep(0.01)

    approver = asyncio.create_task(approve_later())
    await flow2.run({"value": 2})
    await approver

    history = gate.get_history()
    assert len(history) == 2
    assert history[0].status == "approved"
    assert history[0].decided_by == "auto"
    assert history[1].status == "approved"
    assert history[1].decided_by == "human:human"


@pytest.mark.asyncio
async def test_max_auto_approvals():
    """Auto-approval stops after the configured limit."""
    policy = ApprovalPolicy(
        auto_approve_below=RiskLevel.LOW,
        max_auto_approvals=2,
        timeout=0.05,
        timeout_action="deny",
    )
    gate = ApprovalGate(policy=policy)

    # First two LOW risk requests should auto-approve
    for i in range(2):
        task = create_approval_task(
            id=f"limited_{i}",
            risk_level=RiskLevel.LOW,
            gate=gate,
            input_schema=SimpleInput,
            output_schema=SimpleOutput,
        )
        flow = Flow(id=f"limit_{i}", description=f"Limit {i}")
        flow.then(task).register()
        result = await flow.run({"value": i})
        assert result["value"] == i

    # Third LOW risk request should NOT auto-approve (limit reached),
    # and will time out with deny
    task3 = create_approval_task(
        id="limited_2",
        risk_level=RiskLevel.LOW,
        gate=gate,
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
    )
    flow3 = Flow(id="limit_2", description="Limit 2")
    flow3.then(task3).register()

    with pytest.raises(ApprovalDenied):
        await flow3.run({"value": 99})

    history = gate.get_history()
    assert len(history) == 3
    assert history[0].decided_by == "auto"
    assert history[1].decided_by == "auto"
    assert history[2].status == "timed_out"


@pytest.mark.asyncio
async def test_approval_task_in_flow():
    """Approval task works within a multi-step Water flow."""
    gate = ApprovalGate(policy=ApprovalPolicy(auto_approve_below=RiskLevel.MEDIUM))

    class PipeInput(BaseModel):
        message: str

    class PipeOutput(BaseModel):
        message: str

    from water.task import Task

    async def transform_execute(params, context):
        data = params["input_data"]
        return {"message": data["message"].upper()}

    transform_task = Task(
        id="transform",
        description="Uppercase transform",
        input_schema=PipeInput,
        output_schema=PipeOutput,
        execute=transform_execute,
    )

    approval_task = create_approval_task(
        id="approve_step",
        action_description="Approve transformed message",
        risk_level=RiskLevel.LOW,
        gate=gate,
        input_schema=PipeOutput,
        output_schema=PipeOutput,
    )

    flow = Flow(id="pipeline", description="Pipeline with approval")
    flow.then(transform_task).then(approval_task).register()

    result = await flow.run({"message": "hello"})
    assert result["message"] == "HELLO"


@pytest.mark.asyncio
async def test_custom_summary_fn():
    """summary_fn extracts a custom summary from input data."""
    gate = ApprovalGate()

    captured_summaries = []

    original_request = gate.request_approval

    async def capturing_request(task_id, execution_id, action_description, risk_level, data_summary):
        captured_summaries.append(data_summary)
        return await original_request(task_id, execution_id, action_description, risk_level, data_summary)

    gate.request_approval = capturing_request

    def my_summary(data):
        return {"total": data.get("a", 0) + data.get("b", 0)}

    task = create_approval_task(
        id="custom_summary",
        risk_level=RiskLevel.LOW,
        gate=gate,
        summary_fn=my_summary,
    )

    flow = Flow(id="summary_flow", description="Summary flow")
    flow.then(task).register()

    await flow.run({"a": 10, "b": 20})

    assert len(captured_summaries) == 1
    assert captured_summaries[0] == {"total": 30}


@pytest.mark.asyncio
async def test_risk_levels():
    """All risk levels work correctly with appropriate auto-approve thresholds."""
    # Policy: auto-approve at or below MEDIUM
    policy = ApprovalPolicy(auto_approve_below=RiskLevel.MEDIUM, timeout=0.05, timeout_action="deny")
    gate = ApprovalGate(policy=policy)

    # LOW should auto-approve
    task_low = create_approval_task(
        id="rl_low", risk_level=RiskLevel.LOW, gate=gate,
        input_schema=SimpleInput, output_schema=SimpleOutput,
    )
    flow_low = Flow(id="rl_low_f", description="Low")
    flow_low.then(task_low).register()
    result = await flow_low.run({"value": 1})
    assert result["value"] == 1

    # MEDIUM should also auto-approve (at threshold)
    task_med = create_approval_task(
        id="rl_med", risk_level=RiskLevel.MEDIUM, gate=gate,
        input_schema=SimpleInput, output_schema=SimpleOutput,
    )
    flow_med = Flow(id="rl_med_f", description="Medium")
    flow_med.then(task_med).register()
    result = await flow_med.run({"value": 2})
    assert result["value"] == 2

    # HIGH should require approval (times out -> denied)
    task_high = create_approval_task(
        id="rl_high", risk_level=RiskLevel.HIGH, gate=gate,
        input_schema=SimpleInput, output_schema=SimpleOutput,
    )
    flow_high = Flow(id="rl_high_f", description="High")
    flow_high.then(task_high).register()
    with pytest.raises(ApprovalDenied):
        await flow_high.run({"value": 3})

    # CRITICAL should require approval (times out -> denied)
    task_crit = create_approval_task(
        id="rl_crit", risk_level=RiskLevel.CRITICAL, gate=gate,
        input_schema=SimpleInput, output_schema=SimpleOutput,
    )
    flow_crit = Flow(id="rl_crit_f", description="Critical")
    flow_crit.then(task_crit).register()
    with pytest.raises(ApprovalDenied):
        await flow_crit.run({"value": 4})

    history = gate.get_history()
    assert len(history) == 4
    statuses = [r.status for r in history]
    assert statuses[0] == "approved"  # LOW
    assert statuses[1] == "approved"  # MEDIUM
    assert statuses[2] == "timed_out"  # HIGH
    assert statuses[3] == "timed_out"  # CRITICAL
