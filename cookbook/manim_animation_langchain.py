from langchain_openai import ChatOpenAI
from langchain.agents import Tool, AgentType, initialize_agent
from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
from rich.prompt import Prompt
import re

class ManimInput(BaseModel):
    prompt: str
    
class ManimOutput(BaseModel):
    result:str
    
class ManimCodeOutput(BaseModel):
    code:str

llm = ChatOpenAI(model_name="gpt-4o", temperature=0)
structured_llm = llm.with_structured_output(ManimCodeOutput)

def manim_code_generator(prompt: str)->str:
    print(f"\n🔧 [ManimCodeGenerator] Generating manim code for: {prompt}")
    response = structured_llm.invoke(f"""You are a Manim animation expert.
        Return a Python animation code that corresponds to this prompt: "{prompt}"

        Respond ONLY using the structured format provided.
        """)
    print(response)
    return response.code.strip()
    
manim_tool = Tool.from_function(
    name="ManimCodeGenerator",
    description="Generates manim animation code for a given prompt.",
    func=manim_code_generator,
    return_direct=True
)

agent = initialize_agent(
    tools=[manim_tool],
    llm=llm,
    agent_type=AgentType.OPENAI_FUNCTIONS,
    verbose=True
)

def run_manim_generator(params: Dict[str, Any], context) -> Dict[str, str]:
    prompt = params["input_data"]["prompt"]
    result = agent.run(prompt)
    clean_result = re.sub(r"```(?:python)?\n(.*?)```", r"\1", result, flags=re.DOTALL).strip()

    return {"result": clean_result}


manim_generator = create_task(
    id="ManimGenerator",
    execute=run_manim_generator,
    description="Generates manim animation code for a given prompt.",
    input_schema=ManimInput,
    output_schema=ManimOutput
)

manim_flow = Flow(id="manim_flow", description="Manim Animation Generator")
manim_flow.then(manim_generator).register()

async def main():
    prompt = Prompt.ask(
        "[bold]Enter a prompt[/bold] (e.g., 'A manim animation of a cat')",
    )

    result = await manim_flow.run({"prompt": prompt})

    py_file = "manim_animation.py"
    with open(py_file, "w") as f:
        f.write(result["result"])

    print(f"\n✅ Manim code saved to {py_file}")


asyncio.run(main())