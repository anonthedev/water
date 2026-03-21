"""
Cookbook: Approval Gates in Water Flows
=======================================

This example demonstrates how to use Human-on-the-Loop approval gates
in Water workflows. Approval gates let you auto-approve low-risk actions
while requiring manual sign-off for high-risk ones.

Features shown:
- Auto-approve for low-risk actions
- Manual approval for high-risk actions
- Timeout handling with different policies
- A deployment pipeline with approval gates
"""

import asyncio
from pydantic import BaseModel
from water.core import Flow, Task
from water.agents.approval import (
    RiskLevel,
    ApprovalPolicy,
    ApprovalGate,
    ApprovalDenied,
    create_approval_task,
)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class DeployInput(BaseModel):
    service: str
    version: str
    environment: str


class DeployOutput(BaseModel):
    service: str
    version: str
    environment: str
    deployed: bool = False


class TestInput(BaseModel):
    service: str
    version: str
    environment: str


class TestOutput(BaseModel):
    service: str
    version: str
    environment: str
    tests_passed: bool = False


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------

async def run_tests(params, context):
    """Simulate running tests."""
    data = params["input_data"]
    print(f"  Running tests for {data['service']} v{data['version']}...")
    await asyncio.sleep(0.1)  # simulate test run
    return {**data, "tests_passed": True}


async def deploy_service(params, context):
    """Simulate deploying a service."""
    data = params["input_data"]
    print(f"  Deploying {data['service']} v{data['version']} to {data['environment']}...")
    await asyncio.sleep(0.1)  # simulate deploy
    return {**data, "deployed": True}


# --------------------------------------------------------------------------
# Example 1: Basic auto-approve for low-risk actions
# --------------------------------------------------------------------------

async def example_auto_approve():
    """Low-risk actions are auto-approved without human intervention."""
    print("\n=== Example 1: Auto-Approve Low-Risk ===\n")

    gate = ApprovalGate(policy=ApprovalPolicy(
        auto_approve_below=RiskLevel.MEDIUM,  # auto-approve LOW and MEDIUM
    ))

    test_task = Task(
        id="run_tests",
        description="Run test suite",
        input_schema=TestInput,
        output_schema=TestOutput,
        execute=run_tests,
    )

    # Low-risk approval: auto-approved instantly
    approval = create_approval_task(
        id="approve_staging",
        description="Approve staging deploy",
        action_description="Deploy to staging environment",
        risk_level=RiskLevel.LOW,
        gate=gate,
        input_schema=TestOutput,
        output_schema=TestOutput,
    )

    deploy_task = Task(
        id="deploy",
        description="Deploy service",
        input_schema=TestOutput,
        output_schema=DeployOutput,
        execute=deploy_service,
    )

    flow = Flow(id="staging_deploy", description="Staging deployment pipeline")
    flow.then(test_task).then(approval).then(deploy_task).register()

    result = await flow.run({
        "service": "api-gateway",
        "version": "2.1.0",
        "environment": "staging",
    })

    print(f"  Result: deployed={result['deployed']}")
    print(f"  Approval history: {[(r.status, r.decided_by) for r in gate.get_history()]}")


# --------------------------------------------------------------------------
# Example 2: Manual approval for high-risk (production deploy)
# --------------------------------------------------------------------------

async def example_manual_approval():
    """High-risk actions require manual approval."""
    print("\n=== Example 2: Manual Approval for High-Risk ===\n")

    gate = ApprovalGate(policy=ApprovalPolicy(
        auto_approve_below=RiskLevel.LOW,
        timeout=5.0,
        timeout_action="deny",
    ))

    approval = create_approval_task(
        id="approve_prod",
        description="Approve production deploy",
        action_description="Deploy to PRODUCTION",
        risk_level=RiskLevel.HIGH,
        gate=gate,
        input_schema=DeployInput,
        output_schema=DeployInput,
        summary_fn=lambda d: {
            "service": d["service"],
            "version": d["version"],
            "target": d["environment"],
        },
    )

    deploy_task = Task(
        id="deploy_prod",
        description="Deploy to production",
        input_schema=DeployInput,
        output_schema=DeployOutput,
        execute=deploy_service,
    )

    flow = Flow(id="prod_deploy", description="Production deployment")
    flow.then(approval).then(deploy_task).register()

    # Simulate a human approving after a short delay
    async def human_approver():
        for _ in range(100):
            pending = gate.get_pending()
            if pending:
                req = pending[0]
                print(f"  Pending approval: {req.action_description}")
                print(f"  Risk level: {req.risk_level.name}")
                print(f"  Summary: {req.data_summary}")
                gate.approve(req.request_id, decided_by="ops-lead")
                print("  -> Approved by ops-lead")
                return
            await asyncio.sleep(0.05)

    approver = asyncio.create_task(human_approver())
    result = await flow.run({
        "service": "payment-service",
        "version": "3.0.0",
        "environment": "production",
    })
    await approver

    print(f"  Result: deployed={result['deployed']}")


# --------------------------------------------------------------------------
# Example 3: Timeout handling
# --------------------------------------------------------------------------

async def example_timeout_handling():
    """Demonstrates timeout behavior with different policies."""
    print("\n=== Example 3: Timeout Handling ===\n")

    # Policy: auto-approve on timeout (e.g., for non-critical deploys)
    gate_permissive = ApprovalGate(policy=ApprovalPolicy(
        auto_approve_below=RiskLevel.LOW,
        timeout=0.2,
        timeout_action="approve",
    ))

    task_permissive = create_approval_task(
        id="permissive_gate",
        action_description="Deploy monitoring update",
        risk_level=RiskLevel.MEDIUM,
        gate=gate_permissive,
        input_schema=DeployInput,
        output_schema=DeployInput,
    )

    flow_p = Flow(id="permissive", description="Permissive timeout")
    flow_p.then(task_permissive).register()

    result = await flow_p.run({
        "service": "monitoring",
        "version": "1.2.0",
        "environment": "staging",
    })
    print(f"  Permissive gate: status={gate_permissive.get_history()[0].status}, "
          f"decided_by={gate_permissive.get_history()[0].decided_by}")

    # Policy: deny on timeout (e.g., for production deploys)
    gate_strict = ApprovalGate(policy=ApprovalPolicy(
        auto_approve_below=RiskLevel.LOW,
        timeout=0.2,
        timeout_action="deny",
    ))

    task_strict = create_approval_task(
        id="strict_gate",
        action_description="Deploy to production",
        risk_level=RiskLevel.HIGH,
        gate=gate_strict,
        input_schema=DeployInput,
        output_schema=DeployInput,
    )

    flow_s = Flow(id="strict", description="Strict timeout")
    flow_s.then(task_strict).register()

    try:
        await flow_s.run({
            "service": "payment-service",
            "version": "3.0.0",
            "environment": "production",
        })
    except ApprovalDenied as e:
        print(f"  Strict gate: denied on timeout - {e}")


# --------------------------------------------------------------------------
# Example 4: Full deployment pipeline with multiple approval gates
# --------------------------------------------------------------------------

async def example_deployment_pipeline():
    """A complete deployment pipeline with staged approval gates."""
    print("\n=== Example 4: Deployment Pipeline ===\n")

    # Shared gate with auto-approve limit
    gate = ApprovalGate(policy=ApprovalPolicy(
        auto_approve_below=RiskLevel.MEDIUM,
        timeout=2.0,
        timeout_action="deny",
        max_auto_approvals=5,
    ))

    test_task = Task(
        id="tests",
        description="Run tests",
        input_schema=TestInput,
        output_schema=TestOutput,
        execute=run_tests,
    )

    # Staging approval: LOW risk -> auto-approved
    staging_approval = create_approval_task(
        id="staging_gate",
        action_description="Deploy to staging",
        risk_level=RiskLevel.LOW,
        gate=gate,
        input_schema=TestOutput,
        output_schema=TestOutput,
    )

    staging_deploy = Task(
        id="staging_deploy",
        description="Deploy to staging",
        input_schema=TestOutput,
        output_schema=DeployOutput,
        execute=deploy_service,
    )

    # Production approval: CRITICAL risk -> requires manual approval
    prod_approval = create_approval_task(
        id="prod_gate",
        action_description="Deploy to PRODUCTION (critical)",
        risk_level=RiskLevel.CRITICAL,
        gate=gate,
        input_schema=DeployOutput,
        output_schema=DeployOutput,
    )

    async def deploy_prod(params, context):
        data = params["input_data"]
        print(f"  Deploying {data['service']} v{data['version']} to production...")
        return {**data, "environment": "production", "deployed": True}

    prod_deploy = Task(
        id="prod_deploy",
        description="Deploy to production",
        input_schema=DeployOutput,
        output_schema=DeployOutput,
        execute=deploy_prod,
    )

    flow = Flow(id="full_pipeline", description="Full deployment pipeline")
    (flow
        .then(test_task)
        .then(staging_approval)
        .then(staging_deploy)
        .then(prod_approval)
        .then(prod_deploy)
        .register())

    # Simulate human approving the production gate
    async def approve_prod_gate():
        for _ in range(200):
            pending = gate.get_pending()
            if pending:
                req = pending[0]
                print(f"  Manual approval needed: {req.action_description} "
                      f"(risk: {req.risk_level.name})")
                gate.approve(req.request_id, decided_by="release-manager")
                print("  -> Approved by release-manager")
                return
            await asyncio.sleep(0.05)

    approver = asyncio.create_task(approve_prod_gate())

    result = await flow.run({
        "service": "checkout-service",
        "version": "4.0.0",
        "environment": "staging",
    })
    await approver

    print(f"\n  Final result: deployed={result['deployed']}, env={result['environment']}")
    print(f"  Approval history:")
    for req in gate.get_history():
        print(f"    - {req.action_description}: {req.status} by {req.decided_by}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

async def main():
    await example_auto_approve()
    await example_manual_approval()
    await example_timeout_handling()
    await example_deployment_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
