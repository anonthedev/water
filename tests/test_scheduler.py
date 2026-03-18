import pytest
import asyncio
from datetime import datetime, timedelta
from pydantic import BaseModel
from water import create_task, Flow, FlowScheduler
from water.scheduler import _cron_matches, ScheduledJob


class HealthInput(BaseModel):
    url: str


class HealthOutput(BaseModel):
    status: str


def _make_task():
    return create_task(
        id="health_check",
        input_schema=HealthInput,
        output_schema=HealthOutput,
        execute=lambda params, context: {"status": "ok"},
    )


def _make_flow() -> Flow:
    flow = Flow(id="health_flow")
    flow.then(_make_task()).register()
    return flow


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_with_interval():
    scheduler = FlowScheduler()
    flow = _make_flow()
    job_id = scheduler.schedule(flow, {"url": "http://localhost"}, interval_seconds=30)

    assert job_id is not None
    jobs = scheduler.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == job_id
    assert jobs[0]["interval"] == 30
    assert jobs[0]["next_run"] is not None


@pytest.mark.asyncio
async def test_schedule_with_cron():
    scheduler = FlowScheduler()
    flow = _make_flow()
    job_id = scheduler.schedule(flow, {"url": "http://localhost"}, cron_expr="*/5 * * * *")

    jobs = scheduler.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["cron_expr"] == "*/5 * * * *"
    assert jobs[0]["next_run"] is not None


@pytest.mark.asyncio
async def test_unschedule():
    scheduler = FlowScheduler()
    flow = _make_flow()
    job_id = scheduler.schedule(flow, {"url": "http://localhost"}, interval_seconds=60)

    assert len(scheduler.list_jobs()) == 1
    scheduler.unschedule(job_id)
    assert len(scheduler.list_jobs()) == 0

    with pytest.raises(KeyError):
        scheduler.unschedule("nonexistent")


@pytest.mark.asyncio
async def test_list_jobs():
    scheduler = FlowScheduler()
    flow = _make_flow()
    scheduler.schedule(flow, {"url": "http://a"}, interval_seconds=10, job_id="j1")
    scheduler.schedule(flow, {"url": "http://b"}, cron_expr="0 * * * *", job_id="j2")

    jobs = scheduler.list_jobs()
    assert len(jobs) == 2
    ids = {j["job_id"] for j in jobs}
    assert ids == {"j1", "j2"}

    for j in jobs:
        assert j["flow_id"] == "health_flow"


@pytest.mark.asyncio
async def test_tick_runs_due_job():
    scheduler = FlowScheduler()
    flow = _make_flow()
    job_id = scheduler.schedule(flow, {"url": "http://localhost"}, interval_seconds=10)

    # Force the job to be due now
    scheduler._jobs[job_id].next_run = datetime.now() - timedelta(seconds=1)

    await scheduler.tick()

    job = scheduler._jobs[job_id]
    assert job.last_run is not None
    assert job.next_run > datetime.now() - timedelta(seconds=1)


@pytest.mark.asyncio
async def test_tick_skips_not_due():
    scheduler = FlowScheduler()
    flow = _make_flow()
    job_id = scheduler.schedule(flow, {"url": "http://localhost"}, interval_seconds=9999)

    await scheduler.tick()

    job = scheduler._jobs[job_id]
    assert job.last_run is None


def test_cron_matches():
    dt = datetime(2026, 3, 18, 10, 30, 0)  # Wednesday

    # Every minute
    assert _cron_matches("* * * * *", dt) is True

    # Every 5 minutes — 30 % 5 == 0
    assert _cron_matches("*/5 * * * *", dt) is True
    dt2 = dt.replace(minute=31)
    assert _cron_matches("*/5 * * * *", dt2) is False

    # Specific minute
    assert _cron_matches("30 * * * *", dt) is True
    assert _cron_matches("15 * * * *", dt) is False

    # Specific hour
    assert _cron_matches("* 10 * * *", dt) is True
    assert _cron_matches("* 11 * * *", dt) is False

    # Comma-separated values
    assert _cron_matches("30,45 * * * *", dt) is True
    assert _cron_matches("15,45 * * * *", dt) is False

    # Day of week: Wednesday = isoweekday() 3 => cron weekday 3
    assert _cron_matches("* * * * 3", dt) is True
    assert _cron_matches("* * * * 1", dt) is False

    # Invalid expression raises
    with pytest.raises(ValueError):
        _cron_matches("* * *", dt)


@pytest.mark.asyncio
async def test_start_and_stop():
    scheduler = FlowScheduler()
    assert scheduler.running is False

    await scheduler.start()
    assert scheduler.running is True

    await scheduler.stop()
    assert scheduler.running is False


@pytest.mark.asyncio
async def test_schedule_requires_timing():
    scheduler = FlowScheduler()
    flow = _make_flow()
    with pytest.raises(ValueError):
        scheduler.schedule(flow, {"url": "http://localhost"})
