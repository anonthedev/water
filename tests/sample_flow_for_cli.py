"""
A minimal flow module used by CLI tests.
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any


class GreetInput(BaseModel):
    name: str = "World"


class GreetOutput(BaseModel):
    greeting: str


def greet(params: Dict[str, Any], context) -> Dict[str, Any]:
    name = params["input_data"].get("name", "World")
    return {"greeting": f"Hello, {name}!"}


greet_task = create_task(
    id="greet",
    description="Greet the user",
    input_schema=GreetInput,
    output_schema=GreetOutput,
    execute=greet,
)

hello_flow = Flow(id="hello", description="A simple greeting flow", version="1.0.0")
hello_flow.then(greet_task).register()


# A second flow to test `water list`
class FarewellOutput(BaseModel):
    message: str


farewell_task = create_task(
    id="farewell",
    description="Say goodbye",
    input_schema=GreetInput,
    output_schema=FarewellOutput,
    execute=lambda params, ctx: {"message": "Goodbye!"},
)

bye_flow = Flow(id="bye", description="A farewell flow", version="2.0.0")
bye_flow.then(farewell_task).register()
