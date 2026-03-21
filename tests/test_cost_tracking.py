import pytest
import warnings

from water.observability.cost import (
    BudgetExceededError,
    CostSummary,
    CostTracker,
    TaskCost,
    TokenUsage,
)


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------

class TestTokenUsage:
    def test_total_tokens(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_total_tokens_defaults_to_zero(self):
        usage = TokenUsage()
        assert usage.total_tokens == 0


# ---------------------------------------------------------------------------
# CostTracker.calculate_cost
# ---------------------------------------------------------------------------

class TestCalculateCost:
    def test_known_model(self):
        tracker = CostTracker()
        tokens = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = tracker.calculate_cost("gpt-4o", tokens)
        # 1M input * $2.50/1M + 1M output * $10.00/1M = 12.50
        assert cost == pytest.approx(12.50)

    def test_unknown_model_returns_zero(self):
        tracker = CostTracker()
        tokens = TokenUsage(input_tokens=500, output_tokens=500)
        assert tracker.calculate_cost("mystery-model", tokens) == 0.0

    def test_partial_tokens(self):
        tracker = CostTracker()
        tokens = TokenUsage(input_tokens=1000, output_tokens=0)
        cost = tracker.calculate_cost("gpt-4o", tokens)
        # 1000 / 1M * 2.50 = 0.0025
        assert cost == pytest.approx(0.0025)


# ---------------------------------------------------------------------------
# CostTracker.record
# ---------------------------------------------------------------------------

class TestRecord:
    def test_record_adds_entry(self):
        tracker = CostTracker()
        tokens = TokenUsage(input_tokens=500, output_tokens=200)
        entry = tracker.record("task_1", "gpt-4o", tokens)

        assert isinstance(entry, TaskCost)
        assert entry.task_id == "task_1"
        assert entry.model == "gpt-4o"
        assert entry.tokens.total_tokens == 700
        assert entry.cost_usd > 0
        assert entry.timestamp != ""
        assert len(tracker._task_costs) == 1

    def test_record_multiple_entries(self):
        tracker = CostTracker()
        tracker.record("t1", "gpt-4o", TokenUsage(100, 50))
        tracker.record("t2", "gpt-4o-mini", TokenUsage(200, 100))
        assert len(tracker._task_costs) == 2


# ---------------------------------------------------------------------------
# CostSummary
# ---------------------------------------------------------------------------

class TestCostSummary:
    def test_aggregation(self):
        tracker = CostTracker()
        tracker.record("t1", "gpt-4o", TokenUsage(1_000_000, 500_000))
        tracker.record("t2", "gpt-4o-mini", TokenUsage(2_000_000, 1_000_000))

        summary = tracker.get_summary()
        assert summary.total_tokens.input_tokens == 3_000_000
        assert summary.total_tokens.output_tokens == 1_500_000
        assert summary.total_tokens.total_tokens == 4_500_000
        assert summary.total_cost_usd > 0
        assert len(summary.task_costs) == 2

    def test_summary_formatting(self):
        tracker = CostTracker()
        tracker.record("analyze", "gpt-4o", TokenUsage(1000, 500))
        text = tracker.get_summary().summary()

        assert "=== Cost Summary ===" in text
        assert "Total cost:" in text
        assert "Total tokens:" in text
        assert "analyze" in text
        assert "gpt-4o" in text

    def test_to_dict_serialization(self):
        tracker = CostTracker()
        tracker.record("step1", "gpt-4o", TokenUsage(100, 200))
        d = tracker.get_summary().to_dict()

        assert "total_cost_usd" in d
        assert "total_input_tokens" in d
        assert "total_output_tokens" in d
        assert "total_tokens" in d
        assert "tasks" in d
        assert len(d["tasks"]) == 1
        task = d["tasks"][0]
        assert task["task_id"] == "step1"
        assert task["input_tokens"] == 100
        assert task["output_tokens"] == 200


# ---------------------------------------------------------------------------
# Budget limits
# ---------------------------------------------------------------------------

class TestBudgetLimits:
    def test_budget_warn(self):
        tracker = CostTracker(budget_limit=0.001, on_budget_exceeded="warn")
        # Record enough to exceed tiny budget
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tracker.record("big_task", "gpt-4o", TokenUsage(1_000_000, 1_000_000))
            assert len(w) == 1
            assert "Budget exceeded" in str(w[0].message)

    def test_budget_stop_raises(self):
        tracker = CostTracker(budget_limit=0.001, on_budget_exceeded="stop")
        with pytest.raises(BudgetExceededError, match="Budget exceeded"):
            tracker.record("big_task", "gpt-4o", TokenUsage(1_000_000, 1_000_000))


# ---------------------------------------------------------------------------
# Custom pricing & reset
# ---------------------------------------------------------------------------

class TestCustomPricingAndReset:
    def test_custom_pricing(self):
        custom = {"my-model": {"input": 1.00, "output": 2.00}}
        tracker = CostTracker(pricing=custom)
        tokens = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = tracker.calculate_cost("my-model", tokens)
        assert cost == pytest.approx(3.00)

    def test_custom_pricing_overrides_default(self):
        custom = {"gpt-4o": {"input": 5.00, "output": 20.00}}
        tracker = CostTracker(pricing=custom)
        tokens = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = tracker.calculate_cost("gpt-4o", tokens)
        assert cost == pytest.approx(25.00)

    def test_reset_clears_costs(self):
        tracker = CostTracker()
        tracker.record("t1", "gpt-4o", TokenUsage(100, 50))
        tracker.record("t2", "gpt-4o", TokenUsage(200, 100))
        assert len(tracker._task_costs) == 2

        tracker.reset()
        assert len(tracker._task_costs) == 0
        summary = tracker.get_summary()
        assert summary.total_cost_usd == 0.0
        assert summary.total_tokens.total_tokens == 0


# ---------------------------------------------------------------------------
# Middleware interface (async)
# ---------------------------------------------------------------------------

class TestMiddlewareInterface:
    @pytest.mark.asyncio
    async def test_after_task_extracts_usage(self):
        tracker = CostTracker()
        result = {
            "answer": "hello",
            "model": "gpt-4o",
            "usage": {"input_tokens": 50, "output_tokens": 25},
        }
        returned = await tracker.after_task("llm_call", {}, result, None)
        assert returned is result
        assert len(tracker._task_costs) == 1
        assert tracker._task_costs[0].tokens.total_tokens == 75

    @pytest.mark.asyncio
    async def test_after_task_no_usage_does_nothing(self):
        tracker = CostTracker()
        result = {"answer": "hello"}
        await tracker.after_task("plain_task", {}, result, None)
        assert len(tracker._task_costs) == 0

    @pytest.mark.asyncio
    async def test_before_task_passes_through(self):
        tracker = CostTracker()
        data = {"key": "value"}
        out = await tracker.before_task("t1", data, None)
        assert out is data
