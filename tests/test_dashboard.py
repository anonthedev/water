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
async def test_get_stats_empty(dashboard):
    """Empty storage returns zeros for all stat fields."""
    stats = await dashboard.get_stats()
    assert stats["total_sessions"] == 0
    assert stats["by_status"] == {}
    assert stats["recent_sessions"] == []


@pytest.mark.asyncio
async def test_get_stats_with_sessions(storage, dashboard):
    """Stats correctly counts sessions by status."""
    statuses = [
        FlowStatus.COMPLETED,
        FlowStatus.COMPLETED,
        FlowStatus.FAILED,
        FlowStatus.RUNNING,
    ]
    for i, status in enumerate(statuses):
        session = FlowSession(
            flow_id="test_flow",
            input_data={"i": i},
            execution_id=f"exec_{i}",
            status=status,
        )
        await storage.save_session(session)

    stats = await dashboard.get_stats()
    assert stats["total_sessions"] == 4
    assert stats["by_status"]["completed"] == 2
    assert stats["by_status"]["failed"] == 1
    assert stats["by_status"]["running"] == 1
    assert len(stats["recent_sessions"]) == 4
    assert all("execution_id" in s for s in stats["recent_sessions"])


@pytest.mark.asyncio
async def test_get_sessions_list(storage, dashboard):
    """Sessions list returns session dicts with expected fields."""
    for i in range(3):
        session = FlowSession(
            flow_id="list_flow",
            input_data={"v": i},
            execution_id=f"exec_list_{i}",
            status=FlowStatus.COMPLETED,
        )
        await storage.save_session(session)

    result = await dashboard.get_sessions_list()
    assert "sessions" in result
    assert "total" in result
    assert result["total"] == 3
    assert len(result["sessions"]) == 3


@pytest.mark.asyncio
async def test_get_sessions_list_pagination(storage, dashboard):
    """Limit and offset correctly paginate session results."""
    for i in range(10):
        session = FlowSession(
            flow_id="page_flow",
            input_data={"v": i},
            execution_id=f"exec_page_{i}",
            status=FlowStatus.COMPLETED,
        )
        await storage.save_session(session)

    # First page
    result = await dashboard.get_sessions_list(limit=3, offset=0)
    assert len(result["sessions"]) == 3
    assert result["total"] == 10

    # Second page
    result2 = await dashboard.get_sessions_list(limit=3, offset=3)
    assert len(result2["sessions"]) == 3

    # The two pages should have different sessions
    ids_page1 = {s["execution_id"] for s in result["sessions"]}
    ids_page2 = {s["execution_id"] for s in result2["sessions"]}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.asyncio
async def test_get_session_detail(storage, dashboard):
    """Session detail returns session info and task runs."""
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

    detail = await dashboard.get_session_detail("exec_detail")
    assert detail is not None
    assert detail["execution_id"] == "exec_detail"
    assert detail["flow_id"] == "detail_flow"
    assert "task_runs" in detail
    assert len(detail["task_runs"]) == 1
    assert detail["task_runs"][0]["task_id"] == "task_a"


@pytest.mark.asyncio
async def test_get_session_detail_not_found(dashboard):
    """Session detail returns None for a nonexistent execution_id."""
    detail = await dashboard.get_session_detail("nonexistent")
    assert detail is None


@pytest.mark.asyncio
async def test_get_spa_html(dashboard):
    """SPA HTML contains expected markers for React dashboard."""
    html = dashboard.get_spa_html()
    assert isinstance(html, str)
    assert "Water Dashboard" in html
    assert "react" in html.lower()
    assert "tailwindcss" in html.lower()


@pytest.mark.asyncio
async def test_get_flows_summary(dashboard):
    """Flows summary returns info for each flow."""
    # Build a minimal flows dict similar to FlowServer.flows
    # FlowDashboard.get_flows_summary takes the flows dict from the server
    from unittest.mock import MagicMock

    mock_flow = MagicMock()
    mock_flow.id = "summary_flow"
    mock_flow.description = "A test flow"

    flows = {"summary_flow": mock_flow}
    summary = dashboard.get_flows_summary(flows)
    assert isinstance(summary, list)
    assert len(summary) == 1
    assert summary[0]["id"] == "summary_flow"
    assert summary[0]["description"] == "A test flow"
