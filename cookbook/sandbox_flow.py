"""
Sandbox Flow Example: Running User-Provided Code Safely

This example demonstrates how to use Water's sandboxed code execution
to run untrusted or user-provided code in isolated environments with
resource limits, timeout enforcement, and error handling.
"""

import asyncio
from typing import Any, Dict

from pydantic import BaseModel

from water import Flow, create_task
from water.sandbox import (
    InMemorySandbox,
    SubprocessSandbox,
    SandboxConfig,
    SandboxResult,
    create_sandboxed_task,
)


# --- Example 1: Running User-Provided Code Safely ---

async def example_basic_sandbox():
    """Run user-provided code in a sandboxed environment."""
    print("=== Example 1: Basic Sandboxed Execution ===\n")

    # Create a sandboxed task with resource limits
    sandbox_task = create_sandboxed_task(
        id="user_code_runner",
        description="Run user code safely",
        sandbox=SubprocessSandbox(),
        config=SandboxConfig(
            timeout=10.0,        # 10 second timeout
            max_memory_mb=128,   # 128 MB memory limit
            max_output_size=5000, # 5000 char output limit
        ),
    )

    flow = Flow(id="basic_sandbox_flow", description="Run user code safely")
    flow.then(sandbox_task).register()

    # Run some safe code
    result = await flow.run({"code": """
import math
values = [math.sqrt(i) for i in range(10)]
print("Square roots:", values)
__result__ = sum(values)
"""})

    print(f"stdout: {result['stdout']}")
    print(f"return_value: {result['return_value']}")
    print(f"exit_code: {result['exit_code']}")
    print(f"execution_time: {result['execution_time']:.3f}s")
    print()


# --- Example 2: Using SandboxConfig for Resource Limits ---

async def example_resource_limits():
    """Demonstrate timeout enforcement with sandbox config."""
    print("=== Example 2: Resource Limits & Timeout ===\n")

    sandbox = InMemorySandbox()
    config = SandboxConfig(timeout=2.0)

    # This code will timeout
    result = await sandbox.execute(
        "import time; time.sleep(10)",
        config,
    )

    print(f"Timed out: {result.timed_out}")
    print(f"Exit code: {result.exit_code}")
    print(f"stderr: {result.stderr}")
    print()


# --- Example 3: Code Generation + Sandbox Execution Flow ---

class CodeInput(BaseModel):
    prompt: str

class GeneratedCode(BaseModel):
    code: str
    description: str

class ExecutionResult(BaseModel):
    stdout: str
    stderr: str
    return_value: Any = None
    exit_code: int
    execution_time: float


async def example_generate_and_execute():
    """
    A flow that simulates generating code from a prompt
    and then executing it in a sandbox.
    """
    print("=== Example 3: Generate Code + Execute in Sandbox ===\n")

    # Step 1: Simulate code generation (in a real scenario, this would call an LLM)
    def generate_code(params: Dict[str, Any], context) -> Dict[str, Any]:
        prompt = params["input_data"]["prompt"]

        # Simulated code generation based on prompt
        if "fibonacci" in prompt.lower():
            code = """
def fib(n):
    a, b = 0, 1
    result = []
    for _ in range(n):
        result.append(a)
        a, b = b, a + b
    return result

output = fib(10)
print(f"Fibonacci sequence: {output}")
__result__ = output
"""
        else:
            code = f"print('Generated code for: {prompt}')\n__result__ = 'done'"

        return {
            "code": code,
            "description": f"Generated code for: {prompt}",
        }

    code_generator = create_task(
        id="code_generator",
        description="Generate code from a prompt",
        input_schema=CodeInput,
        output_schema=GeneratedCode,
        execute=generate_code,
    )

    # Step 2: Execute the generated code in a sandbox
    sandbox_runner = create_sandboxed_task(
        id="sandbox_runner",
        description="Execute generated code safely",
        sandbox=SubprocessSandbox(),
        config=SandboxConfig(timeout=5.0, max_memory_mb=128),
    )

    flow = Flow(id="gen_and_exec", description="Generate and execute code")
    flow.then(code_generator).then(sandbox_runner).register()

    result = await flow.run({"prompt": "Generate fibonacci sequence"})
    print(f"stdout: {result['stdout']}")
    print(f"return_value: {result['return_value']}")
    print(f"exit_code: {result['exit_code']}")
    print()


# --- Example 4: Error Handling for Sandbox Failures ---

async def example_error_handling():
    """Demonstrate how sandbox handles errors gracefully."""
    print("=== Example 4: Error Handling ===\n")

    sandbox = InMemorySandbox()
    config = SandboxConfig(timeout=5.0)

    # Code that raises an exception
    result = await sandbox.execute(
        "x = 1 / 0",
        config,
    )
    print(f"Division by zero:")
    print(f"  exit_code: {result.exit_code}")
    print(f"  stderr: {result.stderr.splitlines()[-1]}")
    print()

    # Code with a syntax error
    result = await sandbox.execute(
        "def foo(\n",
        config,
    )
    print(f"Syntax error:")
    print(f"  exit_code: {result.exit_code}")
    print(f"  stderr contains SyntaxError: {'SyntaxError' in result.stderr}")
    print()

    # Code that produces output before failing
    result = await sandbox.execute(
        "print('before error')\nraise RuntimeError('oops')",
        config,
    )
    print(f"Partial output before error:")
    print(f"  stdout: {result.stdout.strip()}")
    print(f"  exit_code: {result.exit_code}")
    print(f"  error: {'RuntimeError' in result.stderr}")
    print()


async def main():
    await example_basic_sandbox()
    await example_resource_limits()
    await example_generate_and_execute()
    await example_error_handling()


if __name__ == "__main__":
    asyncio.run(main())
