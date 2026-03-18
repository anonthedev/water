import pytest
from pydantic import BaseModel
from water import create_task, Flow


class DummyInput(BaseModel):
    value: int = 0


class DummyOutput(BaseModel):
    value: int = 0


def _make_task(task_id: str):
    async def execute(params, context):
        return {"value": params["input_data"].get("value", 0)}

    return create_task(
        id=task_id,
        description=f"Task {task_id}",
        input_schema=DummyInput,
        output_schema=DummyOutput,
        execute=execute,
    )


class TestVisualizeSequential:
    def test_visualize_sequential(self):
        task_a = _make_task("task_a")
        flow = Flow(id="seq_flow")
        flow.then(task_a).register()

        result = flow.visualize()

        assert result.startswith("graph TD")
        assert "task_a" in result
        assert "-->" not in result.split("\n")[1]  # first node has no incoming arrow

    def test_visualize_two_sequential(self):
        task_a = _make_task("task_a")
        task_b = _make_task("task_b")
        flow = Flow(id="seq_flow")
        flow.then(task_a).then(task_b).register()

        result = flow.visualize()

        assert "task_a" in result
        assert "task_b" in result
        assert "-->" in result


class TestVisualizeParallel:
    def test_visualize_parallel(self):
        task_a = _make_task("task_a")
        task_b = _make_task("task_b")
        flow = Flow(id="par_flow")
        flow.parallel([task_a, task_b]).register()

        result = flow.visualize()

        assert "graph TD" in result
        assert "fork" in result
        assert "join" in result
        assert "task_a" in result
        assert "task_b" in result
        # fork connects to both tasks, both tasks connect to join
        lines = result.split("\n")
        arrow_lines = [l for l in lines if "-->" in l]
        assert len(arrow_lines) == 4  # fork->a, fork->b, a->join, b->join


class TestVisualizeBranch:
    def test_visualize_branch(self):
        task_a = _make_task("task_a")
        task_b = _make_task("task_b")

        def is_high(data):
            return data.get("value", 0) > 10

        def is_low(data):
            return data.get("value", 0) <= 10

        flow = Flow(id="branch_flow")
        flow.branch([(is_high, task_a), (is_low, task_b)]).register()

        result = flow.visualize()

        assert "graph TD" in result
        # Diamond decision node uses { } syntax
        assert "{" in result
        # Condition labels
        assert "is_high" in result
        assert "is_low" in result
        assert "task_a" in result
        assert "task_b" in result
        assert "end_branch" in result


class TestVisualizeLoop:
    def test_visualize_loop(self):
        task_a = _make_task("task_a")

        def keep_going(data):
            return data.get("value", 0) < 100

        flow = Flow(id="loop_flow")
        flow.loop(keep_going, task_a).register()

        result = flow.visualize()

        assert "graph TD" in result
        assert "task_a" in result
        # Loop-back arrow with condition label
        lines = result.split("\n")
        loop_arrows = [l for l in lines if "-->|keep_going|" in l]
        assert len(loop_arrows) == 1
        # The loop arrow points back to itself
        parts = loop_arrows[0].strip().split()
        assert parts[0] == parts[-1]  # same node id on both sides


class TestVisualizeMap:
    def test_visualize_map(self):
        task_a = _make_task("task_a")
        flow = Flow(id="map_flow")
        flow.map(task_a, over="items").register()

        result = flow.visualize()

        assert "graph TD" in result
        assert "task_a" in result
        assert "map over items" in result


class TestVisualizeDag:
    def test_visualize_dag(self):
        task_a = _make_task("task_a")
        task_b = _make_task("task_b")
        task_c = _make_task("task_c")

        flow = Flow(id="dag_flow")
        flow.dag(
            [task_a, task_b, task_c],
            dependencies={"task_c": ["task_a", "task_b"]},
        ).register()

        result = flow.visualize()

        assert "graph TD" in result
        assert "task_a" in result
        assert "task_b" in result
        assert "task_c" in result
        # task_a --> task_c and task_b --> task_c
        lines = result.split("\n")
        arrow_lines = [l for l in lines if "-->" in l]
        assert len(arrow_lines) == 2


class TestVisualizeRequiresRegistration:
    def test_visualize_requires_registration(self):
        task_a = _make_task("task_a")
        flow = Flow(id="unreg_flow")
        flow.then(task_a)

        with pytest.raises(RuntimeError, match="registered"):
            flow.visualize()


class TestVisualizeInvalidFormat:
    def test_visualize_invalid_format(self):
        task_a = _make_task("task_a")
        flow = Flow(id="fmt_flow")
        flow.then(task_a).register()

        with pytest.raises(ValueError, match="Unsupported visualization format"):
            flow.visualize(format="graphviz")


class TestVisualizeComplexFlow:
    def test_visualize_complex_flow(self):
        """A chain of different node types produces valid connected mermaid."""
        task_a = _make_task("task_a")
        task_b = _make_task("task_b")
        task_c = _make_task("task_c")
        task_d = _make_task("task_d")
        task_e = _make_task("task_e")

        def always_true(data):
            return True

        def keep_going(data):
            return data.get("value", 0) < 5

        flow = Flow(id="complex_flow")
        flow.then(task_a)
        flow.parallel([task_b, task_c])
        flow.branch([(always_true, task_d)])
        flow.loop(keep_going, task_e)
        flow.register()

        result = flow.visualize()

        assert result.startswith("graph TD")
        assert "task_a" in result
        assert "task_b" in result
        assert "task_c" in result
        assert "task_d" in result
        assert "task_e" in result
        assert "fork" in result
        assert "join" in result
        assert "end_branch" in result
        assert "keep_going" in result

        # Every node type should produce at least one connection arrow
        lines = result.split("\n")
        arrow_lines = [l for l in lines if "-->" in l]
        # sequential(a->fork), fork->b, fork->c, b->join, c->join,
        # join->decision, decision->d, d->end_branch, end_branch->e, e->e
        assert len(arrow_lines) >= 10
