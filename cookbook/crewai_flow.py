"""
Research report generator using CrewAI agents orchestrated by Water.

Demonstrates a sequential flow where:
1. A researcher agent gathers information on a topic
2. An analyst agent evaluates and synthesizes the research
3. A writer agent produces a polished report

pip install crewai water-ai
"""

import asyncio
from typing import Any, Dict

from crewai import Agent, Crew, Task as CrewTask
from pydantic import BaseModel

from water import Flow, create_task


# --- Pydantic Schemas ---

class TopicInput(BaseModel):
    topic: str

class ResearchOutput(BaseModel):
    findings: str

class AnalysisOutput(BaseModel):
    analysis: str

class ReportOutput(BaseModel):
    report: str


# --- CrewAI Agents ---

researcher = Agent(
    role="Senior Research Analyst",
    goal="Find comprehensive, accurate information on the given topic",
    backstory=(
        "You are an experienced research analyst who excels at finding "
        "relevant information from diverse sources and presenting it clearly."
    ),
    verbose=False,
)

analyst = Agent(
    role="Data Analyst",
    goal="Synthesize research findings into actionable insights",
    backstory=(
        "You are a skilled analyst who can identify patterns, draw conclusions, "
        "and provide balanced perspectives on complex topics."
    ),
    verbose=False,
)

writer = Agent(
    role="Technical Writer",
    goal="Produce clear, well-structured reports from analytical inputs",
    backstory=(
        "You are an expert technical writer who transforms complex analysis "
        "into readable, professional reports with clear recommendations."
    ),
    verbose=False,
)


# --- Task Execution Functions ---

def research_topic(params: Dict[str, Any], context) -> Dict[str, str]:
    """Use CrewAI researcher agent to gather information."""
    topic = params["input_data"]["topic"]

    crew_task = CrewTask(
        description=f"Research the topic: {topic}. Find key facts, recent developments, and expert opinions.",
        expected_output="Detailed research findings with sources",
        agent=researcher,
    )

    crew = Crew(agents=[researcher], tasks=[crew_task], verbose=False)
    result = crew.kickoff()

    return {"findings": str(result)}


def analyze_research(params: Dict[str, Any], context) -> Dict[str, str]:
    """Use CrewAI analyst agent to synthesize findings."""
    findings = params["input_data"]["findings"]

    crew_task = CrewTask(
        description=(
            f"Analyze the following research findings and identify key themes, "
            f"patterns, and actionable insights:\n\n{findings}"
        ),
        expected_output="Structured analysis with key insights and recommendations",
        agent=analyst,
    )

    crew = Crew(agents=[analyst], tasks=[crew_task], verbose=False)
    result = crew.kickoff()

    return {"analysis": str(result)}


def write_report(params: Dict[str, Any], context) -> Dict[str, str]:
    """Use CrewAI writer agent to produce a final report."""
    analysis = params["input_data"]["analysis"]
    original_topic = context.initial_input.get("topic", "Unknown Topic")

    crew_task = CrewTask(
        description=(
            f"Write a professional report on '{original_topic}' using this analysis:\n\n{analysis}\n\n"
            f"Include an executive summary, key findings, and recommendations."
        ),
        expected_output="A polished, well-structured report in markdown format",
        agent=writer,
    )

    crew = Crew(agents=[writer], tasks=[crew_task], verbose=False)
    result = crew.kickoff()

    return {"report": str(result)}


# --- Water Tasks ---

research_task = create_task(
    id="research",
    description="Research a topic using CrewAI researcher agent",
    execute=research_topic,
    input_schema=TopicInput,
    output_schema=ResearchOutput,
)

analysis_task = create_task(
    id="analyze",
    description="Analyze research findings using CrewAI analyst agent",
    execute=analyze_research,
    input_schema=ResearchOutput,
    output_schema=AnalysisOutput,
)

report_task = create_task(
    id="write_report",
    description="Write a polished report using CrewAI writer agent",
    execute=write_report,
    input_schema=AnalysisOutput,
    output_schema=ReportOutput,
)


# --- Water Flow ---

research_flow = Flow(
    id="crewai_research_flow",
    description="Sequential research report pipeline using CrewAI agents",
)
research_flow.then(research_task).then(analysis_task).then(report_task).register()


async def main():
    topic = input("Enter a research topic: ").strip() or "The impact of AI on software development"

    print(f"\nGenerating research report on: '{topic}'\n")

    result = await research_flow.run({"topic": topic})

    print("\n" + "=" * 80)
    print("Report:")
    print("=" * 80 + "\n")
    print(result["report"])


if __name__ == "__main__":
    asyncio.run(main())
