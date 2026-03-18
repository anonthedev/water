import pytest
from datetime import datetime, timedelta
from water import FlowDashboard, InMemoryStorage, FlowSession, FlowStatus, TaskRun


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def dashboard(storage):
    return FlowDashboard(storage)


@pytest.mark.asyncio
async def test_dashboard_empty(dashboard):
    """Empty storage produces valid HTML with no-sessions message."""
    html = await dashboard.get_dashboard_html()
    assert "<!DOCTYPE html>" in html
    assert "Water Flow Dashboard" in html
    assert "No sessions found." in html


@pytest.mark.asyncio
async def test_dashboard_with_sessions(storage, dashboard):
    """Dashboard HTML shows session data when sessions exist."""
    session = FlowSession(
        flow_id="my_flow",
        input_data={"x": 1},
        execution_id="exec_001",
        status=FlowStatus.COMPLETED,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
    )
    await storage.save_session(session)

    session2 = FlowSession(
        flow_id="my_flow",
        input_data={"x": 2},
        execution_id="exec_002",
        status=FlowStatus.FAILED,
        error="something broke",
        created_at=datetime(2025, 1, 2, 12, 0, 0),
    )
    await storage.save_session(session2)

    html = await dashboard.get_dashboard_html()
    assert "exec_001" in html
    assert "exec_002" in html
    assert "my_flow" in html
    # Status badges present
    assert "completed" in html
    assert "failed" in html
    # Color-coded badges
    assert "#28a745" in html  # green for completed
    assert "#dc3545" in html  # red for failed


@pytest.mark.asyncio
async def test_session_detail(storage, dashboard):
    """Detail page shows session info and task runs."""
    session = FlowSession(
        flow_id="detail_flow",
        input_data={"query": "hello"},
        execution_id="exec_detail",
        status=FlowStatus.COMPLETED,
        result={"answer": "world"},
    )
    await storage.save_session(session)

    now = datetime.utcnow()
    task_run = TaskRun(
        execution_id="exec_detail",
        task_id="task_a",
        node_index=0,
        status="completed",
        input_data={"query": "hello"},
        output_data={"answer": "world"},
        started_at=now - timedelta(seconds=2),
        completed_at=now,
    )
    await storage.save_task_run(task_run)

    html = await dashboard.get_session_detail_html("exec_detail")
    assert "detail_flow" in html
    assert "exec_detail" in html
    assert "task_a" in html
    assert "hello" in html
    assert "world" in html
    # Should contain result section
    assert "Result" in html


@pytest.mark.asyncio
async def test_session_detail_not_found(dashboard):
    """Detail page for missing session shows not-found message."""
    html = await dashboard.get_session_detail_html("nonexistent")
    assert "Session not found." in html


@pytest.mark.asyncio
async def test_stats(storage, dashboard):
    """Stats returns correct total count and recent sessions."""
    for i in range(3):
        session = FlowSession(
            flow_id="stats_flow",
            input_data={"i": i},
            execution_id=f"exec_s{i}",
            status=FlowStatus.COMPLETED,
        )
        await storage.save_session(session)

    stats = await dashboard.get_stats()
    assert stats["total_sessions"] == 3
    assert len(stats["recent_sessions"]) == 3
    # Each recent session is a dict with execution_id
    assert all("execution_id" in s for s in stats["recent_sessions"])


@pytest.mark.asyncio
async def test_stats_by_status(storage, dashboard):
    """Stats counts sessions correctly by status."""
    statuses = [
        FlowStatus.COMPLETED,
        FlowStatus.COMPLETED,
        FlowStatus.FAILED,
        FlowStatus.RUNNING,
    ]
    for i, status in enumerate(statuses):
        session = FlowSession(
            flow_id="count_flow",
            input_data={},
            execution_id=f"exec_c{i}",
            status=status,
        )
        await storage.save_session(session)

    stats = await dashboard.get_stats()
    assert stats["total_sessions"] == 4
    assert stats["by_status"]["completed"] == 2
    assert stats["by_status"]["failed"] == 1
    assert stats["by_status"]["running"] == 1
