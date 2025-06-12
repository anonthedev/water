import pytest
import asyncio
from pydantic import BaseModel
from water import create_task
from water.flow import Flow


# --- Test Schemas ---

class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int

# --- Flow Initialization Tests ---

def test_flow_auto_generated_id():
    flow = Flow(id="test_flow", description="Test flow with auto-generated ID")
    assert flow.id == "test_flow"
    assert flow.description == "Test flow with auto-generated ID"

def test_flow_custom_id_description():
    flow = Flow(id="custom_flow", description="Custom flow with explicit description")
    assert flow.id == "custom_flow"
    assert flow.description == "Custom flow with explicit description"

# --- Task Validation Tests ---

def test_then_none_task():
    flow = Flow(id="test_flow", description="Test flow for None task")
    with pytest.raises(ValueError, match="Task cannot be None"):
        flow.then(None)

def test_empty_flow_registration():
    flow = Flow(id="test_flow", description="Test flow for empty registration")
    with pytest.raises(ValueError, match="Flow must have at least one task"):
        flow.register()

# --- Tests ---

@pytest.mark.asyncio
async def test_sequential_flow_success():
    add_one = create_task(
        id="add_one",
        description="Add one to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    double = create_task(
        id="double",
        description="Double the input value",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] * 2}
    )

    flow = Flow(id="simple_flow", description="Add one, then double")
    flow.then(add_one).then(double).register()

    result = await flow.run({"value": 3})
    assert result["value"] == 8  # (3 + 1) * 2

@pytest.mark.asyncio
async def test_flow_requires_registration():
    add_one = create_task(
        id="add_one",
        description="Add one to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    flow = Flow(id="unregistered_flow", description="Flow that should fail without registration")
    flow.then(add_one)
    with pytest.raises(RuntimeError, match="Flow must be registered"):
        await flow.run({"value": 1})

def test_cannot_add_after_register():
    add_one = create_task(
        id="add_one",
        description="Add one to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    flow = Flow(id="no_add_after_register", description="Test adding after registration")
    flow.then(add_one).register()
    with pytest.raises(RuntimeError, match="Cannot add tasks after registration"):
        flow.then(add_one)

@pytest.mark.asyncio
async def test_complex_flow_with_regular_functions():
    def multiply_and_add(params, context):
        v = params["input_data"]["value"]
        return {"value": v * 2 + 5}

    def subtract_three(params, context):
        v = params["input_data"]["value"]
        return {"value": v - 3}

    task1 = create_task(
        id="multiply_add",
        description="Multiply by 2 and add 5",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=multiply_and_add
    )

    task2 = create_task(
        id="subtract_three",
        description="Subtract 3 from the result",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=subtract_three
    )

    flow = Flow(id="complex_flow", description="Multiply/add, then subtract")
    flow.then(task1).then(task2).register()

    result = await flow.run({"value": 4})
    assert result["value"] == 10  # (4*2+5)=13, 13-3=10

@pytest.mark.asyncio
async def test_branching_flow():
    def high_task(params, context):
        return {"value": params["input_data"]["value"] * 2}

    def low_task(params, context):
        return {"value": params["input_data"]["value"] + 1}

    task1 = create_task(
        id="initial_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )

    task2 = create_task(
        id="high_task",
        description="Double the value for high inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=high_task
    )

    task3 = create_task(
        id="low_task",
        description="Add 1 for low inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=low_task
    )

    flow = Flow(id="branching_flow", description="Test branching logic")
    flow.then(task1).branch([
        (lambda data: data["value"] > 10, task2),
        (lambda data: data["value"] <= 10, task3)
    ]).register()

    # Test high branch
    result = await flow.run({"value": 8})
    assert result["value"] == 26  # (8 + 5) > 10, so high_task: 13 * 2

    # Test low branch
    result = await flow.run({"value": 2})
    assert result["value"] == 8  # (2 + 5) <= 10, so low_task: 7 + 1

@pytest.mark.asyncio
async def test_empty_branch_list():
    task1 = create_task(
        id="initial_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    flow = Flow(id="empty_branch_flow", description="Test empty branch list")
    with pytest.raises(ValueError, match="Branch list cannot be empty"):
        flow.then(task1).branch([]).register()

@pytest.mark.asyncio
async def test_no_matching_branch():
    task1 = create_task(
        id="initial_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    task2 = create_task(
        id="high_task",
        description="Double the value for high inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] * 2}
    )
    task3 = create_task(
        id="low_task",
        description="Add 1 for low inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    task4 = create_task(
        id="final_task",
        description="Add 5 to the final value",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    flow = Flow(id="no_match_flow", description="Test no matching branch")
    flow.then(task1).branch([
        (lambda data: data["value"] > 100, task2),
        (lambda data: data["value"] < 0, task3)
    ]).then(task4).register()
    result = await flow.run({"value": 50})
    assert result["value"] == 60  # task1: 50 + 5, then task4: 55 + 5

@pytest.mark.asyncio
async def test_async_branch_condition():
    async def async_condition(data):
        await asyncio.sleep(0.01)
        return data["value"] > 10

    task1 = create_task(
        id="initial_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    task2 = create_task(
        id="high_task",
        description="Double the value for high inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] * 2}
    )
    task3 = create_task(
        id="low_task",
        description="Add 1 for low inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    flow = Flow(id="async_branch_flow", description="Test async branch condition")
    with pytest.raises(ValueError, match="Branch conditions cannot be async functions"):
        flow.then(task1).branch([
            (async_condition, task2),
            (lambda data: data["value"] <= 10, task3)
        ]).register()

@pytest.mark.asyncio
async def test_branch_condition_exception():
    def failing_condition(data):
        raise RuntimeError("Condition failed")

    task1 = create_task(
        id="initial_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    task2 = create_task(
        id="high_task",
        description="Double the value for high inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] * 2}
    )
    task3 = create_task(
        id="low_task",
        description="Add 1 for low inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    flow = Flow(id="branch_exception_flow", description="Test branch condition exception")
    flow.then(task1).branch([
        (failing_condition, task2),
        (lambda data: data["value"] <= 10, task3)
    ]).register()
    with pytest.raises(RuntimeError, match="Condition failed"):
        await flow.run({"value": 8})

@pytest.mark.asyncio
async def test_branch_task_exception():
    failing_task = create_task(
        id="failing_task",
        description="Task that raises an exception",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: (_ for _ in ()).throw(RuntimeError("Task failed"))
    )

    task1 = create_task(
        id="initial_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    task3 = create_task(
        id="low_task",
        description="Add 1 for low inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    flow = Flow(id="branch_task_exception_flow", description="Test branch task exception")
    flow.then(task1).branch([
        (lambda data: data["value"] > 10, failing_task),
        (lambda data: data["value"] <= 10, task3)
    ]).register()
    with pytest.raises(RuntimeError, match="Task failed"):
        await flow.run({"value": 8})

@pytest.mark.asyncio
async def test_branch_invalid_task():
    task1 = create_task(
        id="initial_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    task3 = create_task(
        id="low_task",
        description="Add 1 for low inputs",
        input_schema=NumberOutput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    flow = Flow(id="invalid_task_flow", description="Test branch with invalid task")
    with pytest.raises(ValueError, match="Task cannot be None"):
        flow.then(task1).branch([
            (lambda data: data["value"] > 10, None),
            (lambda data: data["value"] <= 10, task3)
        ]).register()

@pytest.mark.asyncio
async def test_parallel_execution():
    # Create tasks that modify different parts of the input
    add_task = create_task(
        id="add_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    
    multiply_task = create_task(
        id="multiply_task",
        description="Multiply input by 2",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] * 2}
    )
    
    # Create a flow that runs tasks in parallel
    flow = Flow(id="parallel_flow", description="Test parallel task execution")
    flow.parallel([add_task, multiply_task]).register()
    
    # Run the flow
    result = await flow.run({"value": 10})
    
    # Verify that results are organized by task ID
    assert "add_task" in result
    assert "multiply_task" in result
    assert result["add_task"]["value"] == 15  # 10 + 5
    assert result["multiply_task"]["value"] == 20  # 10 * 2

@pytest.mark.asyncio
async def test_parallel_with_async_tasks():
    async def async_add(params, context):
        await asyncio.sleep(0.1)  # Simulate async work
        return {"value": params["input_data"]["value"] + 5}
    
    async def async_multiply(params, context):
        await asyncio.sleep(0.1)  # Simulate async work
        return {"value": params["input_data"]["value"] * 2}
    
    add_task = create_task(
        id="async_add_task",
        description="Async add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=async_add
    )
    
    multiply_task = create_task(
        id="async_multiply_task",
        description="Async multiply input by 2",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=async_multiply
    )
    
    flow = Flow(id="async_parallel_flow", description="Test parallel async task execution")
    flow.parallel([add_task, multiply_task]).register()
    
    # Run the flow and measure execution time
    start_time = asyncio.get_event_loop().time()
    result = await flow.run({"value": 10})
    end_time = asyncio.get_event_loop().time()
    
    # Verify results are organized by task ID
    assert "async_add_task" in result
    assert "async_multiply_task" in result
    assert result["async_add_task"]["value"] == 15  # 10 + 5
    assert result["async_multiply_task"]["value"] == 20  # 10 * 2
    
    # Verify that tasks ran in parallel (total time should be ~0.1s, not ~0.2s)
    execution_time = end_time - start_time
    assert execution_time < 0.15  # Allow some overhead

@pytest.mark.asyncio
async def test_parallel_with_different_output_keys():
    # Create tasks that return different output keys
    task1 = create_task(
        id="sum_task",
        description="Calculate sum",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"sum": params["input_data"]["value"] + 5}
    )
    
    task2 = create_task(
        id="product_task",
        description="Calculate product",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"product": params["input_data"]["value"] * 2}
    )
    
    flow = Flow(id="different_keys_flow", description="Test parallel tasks with different output keys")
    flow.parallel([task1, task2]).register()
    
    result = await flow.run({"value": 10})
    
    # Verify that each task's output is preserved under its ID
    assert "sum_task" in result
    assert "product_task" in result
    assert result["sum_task"]["sum"] == 15  # 10 + 5
    assert result["product_task"]["product"] == 20  # 10 * 2

@pytest.mark.asyncio
async def test_empty_parallel_list():
    flow = Flow(id="empty_parallel_flow", description="Test empty parallel task list")
    with pytest.raises(ValueError, match="Parallel task list cannot be empty"):
        flow.parallel([]).register()

@pytest.mark.asyncio
async def test_parallel_with_none_task():
    add_task = create_task(
        id="add_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    
    flow = Flow(id="none_parallel_flow", description="Test parallel with None task")
    with pytest.raises(ValueError, match="Task cannot be None"):
        flow.parallel([add_task, None]).register()

@pytest.mark.asyncio
async def test_parallel_task_exception():
    failing_task = create_task(
        id="failing_task",
        description="Task that raises an exception",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: (_ for _ in ()).throw(RuntimeError("Task failed"))
    )
    
    add_task = create_task(
        id="add_task",
        description="Add 5 to the input value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    
    flow = Flow(id="parallel_exception_flow", description="Test parallel task exception")
    flow.parallel([failing_task, add_task]).register()
    
    with pytest.raises(RuntimeError, match="Task failed"):
        await flow.run({"value": 10})

@pytest.mark.asyncio
async def test_loop():
    # Create a task that increments a counter
    increment_task = create_task(
        id="increment",
        description="Increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    
    # Create a flow with a loop that runs until the counter reaches 5
    flow = Flow(id="loop_flow", description="Test loop")
    flow.loop(
        condition=lambda data: data["value"] < 5,
        task=increment_task
    ).register()
    
    # Run the flow with an initial value of 0
    result = await flow.run({"value": 0})
    
    # The result should be 5 (0 -> 1 -> 2 -> 3 -> 4 -> 5)
    assert result["value"] == 5

@pytest.mark.asyncio
async def test_loop_with_max_iterations():
    # Create a task that increments a counter
    increment_task = create_task(
        id="increment",
        description="Increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    
    # Create a flow with a loop that would run forever without max_iterations
    flow = Flow(id="max_iterations_flow", description="Test loop with max iterations")
    flow.loop(
        condition=lambda data: True,  # Always true condition
        task=increment_task,
        max_iterations=3  # Limit to 3 iterations
    ).register()
    
    # Run the flow with an initial value of 0
    result = await flow.run({"value": 0})
    
    # The result should be 3 (0 -> 1 -> 2 -> 3)
    assert result["value"] == 3

@pytest.mark.asyncio
async def test_loop_with_complex_condition():
    # Create a task that doubles the value
    double_task = create_task(
        id="double",
        description="Double the value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] * 2}
    )
    
    # Create a flow with a loop that runs until the value exceeds 100
    flow = Flow(id="complex_condition_flow", description="Test loop with complex condition")
    flow.loop(
        condition=lambda data: data["value"] < 100,
        task=double_task
    ).register()
    
    # Run the flow with an initial value of 5
    result = await flow.run({"value": 5})
    
    # The result should be 160 (5 -> 10 -> 20 -> 40 -> 80 -> 160)
    assert result["value"] == 160

@pytest.mark.asyncio
async def test_loop_never_executes():
    # Create a task that increments a counter
    increment_task = create_task(
        id="increment",
        description="Increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    
    # Create a flow with a loop that never executes because condition is false
    flow = Flow(id="never_executes_flow", description="Test loop that never executes")
    flow.loop(
        condition=lambda data: data["value"] < 0,  # Condition is false from the start
        task=increment_task
    ).register()
    
    # Run the flow with an initial value of 5
    result = await flow.run({"value": 5})
    
    # The result should remain 5 since the loop never executes
    assert result["value"] == 5

@pytest.mark.asyncio
async def test_loop_with_async_task():
    # Create an async task that increments a counter
    async def async_increment(params, context):
        await asyncio.sleep(0.01)  # Simulate async work
        return {"value": params["input_data"]["value"] + 1}
    
    increment_task = create_task(
        id="async_increment",
        description="Async increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=async_increment
    )
    
    # Create a flow with a loop using async task
    flow = Flow(id="async_loop_flow", description="Test loop with async task")
    flow.loop(
        condition=lambda data: data["value"] < 3,
        task=increment_task
    ).register()
    
    # Run the flow with an initial value of 0
    result = await flow.run({"value": 0})
    
    # The result should be 3 (0 -> 1 -> 2 -> 3)
    assert result["value"] == 3

@pytest.mark.asyncio
async def test_loop_with_error():
    # Create a task that fails after a certain number of iterations
    def failing_task(params, context):
        if params["input_data"]["value"] >= 3:
            raise RuntimeError("Task failed after 3 iterations")
        return {"value": params["input_data"]["value"] + 1}
    
    increment_task = create_task(
        id="increment",
        description="Increment until failure",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=failing_task
    )
    
    # Create a flow with a loop
    flow = Flow(id="loop_error_flow", description="Test loop with error")
    flow.loop(
        condition=lambda data: data["value"] < 5,
        task=increment_task
    ).register()
    
    # Run the flow with an initial value of 0
    with pytest.raises(RuntimeError, match="Task failed after 3 iterations"):
        await flow.run({"value": 0})

@pytest.mark.asyncio
async def test_loop_condition_exception():
    # Create a condition that fails
    def failing_condition(data):
        if data["value"] >= 2:
            raise RuntimeError("Condition failed")
        return data["value"] < 5
    
    increment_task = create_task(
        id="increment",
        description="Increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    
    # Create a flow with a loop with failing condition
    flow = Flow(id="condition_error_flow", description="Test loop with condition error")
    flow.loop(
        condition=failing_condition,
        task=increment_task
    ).register()
    
    # Run the flow with an initial value of 0
    with pytest.raises(RuntimeError, match="Condition failed"):
        await flow.run({"value": 0})

@pytest.mark.asyncio
async def test_loop_with_async_condition():
    # Test that async conditions are rejected
    async def async_condition(data):
        await asyncio.sleep(0.01)
        return data["value"] < 5
    
    increment_task = create_task(
        id="increment",
        description="Increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    
    flow = Flow(id="async_condition_flow", description="Test loop with async condition")
    with pytest.raises(ValueError, match="Loop conditions cannot be async functions"):
        flow.loop(
            condition=async_condition,
            task=increment_task
        ).register()

def test_loop_with_none_task():
    flow = Flow(id="none_task_flow", description="Test loop with None task")
    with pytest.raises(ValueError, match="Task cannot be None"):
        flow.loop(
            condition=lambda data: data["value"] < 5,
            task=None
        ).register()

@pytest.mark.asyncio
async def test_sequential_then_loop():
    # Test combining sequential tasks with loop
    add_five_task = create_task(
        id="add_five",
        description="Add 5 to the value",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 5}
    )
    
    increment_task = create_task(
        id="increment",
        description="Increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    
    # Create a flow that first adds 5, then increments while value < 10
    flow = Flow(id="sequential_loop_flow", description="Test sequential then loop")
    flow.then(add_five_task).loop(
        condition=lambda data: data["value"] < 10,
        task=increment_task
    ).register()
    
    # Run the flow with an initial value of 2
    result = await flow.run({"value": 2})
    
    # The result should be 10 (2 -> 7 -> 8 -> 9 -> 10)
    assert result["value"] == 10

@pytest.mark.asyncio
async def test_loop_then_sequential():
    # Test combining loop with sequential tasks
    increment_task = create_task(
        id="increment",
        description="Increment the counter",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] + 1}
    )
    
    multiply_by_two_task = create_task(
        id="multiply_by_two",
        description="Multiply by 2",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, context: {"value": params["input_data"]["value"] * 2}
    )
    
    # Create a flow that increments while value < 5, then multiplies by 2
    flow = Flow(id="loop_sequential_flow", description="Test loop then sequential")
    flow.loop(
        condition=lambda data: data["value"] < 5,
        task=increment_task
    ).then(multiply_by_two_task).register()
    
    # Run the flow with an initial value of 2
    result = await flow.run({"value": 2})
    
    # The result should be 10 (2 -> 3 -> 4 -> 5, then 5 * 2 = 10)
    assert result["value"] == 10

@pytest.mark.asyncio
async def test_original_input_data_available_in_context():
    def access_original_input(params, context):
        assert params["input_data"] == {"value": 42}, "Original input data not found in params"
        return {"value": params["input_data"]["value"] + 10}

    task = create_task(
        id="check_input",
        description="Check access to original input in context",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=access_original_input
    )

    flow = Flow(id="test_input_context", description="Test input data in context")
    flow.then(task).register()

    result = await flow.run({"value": 42})
    assert result["value"] == 52
