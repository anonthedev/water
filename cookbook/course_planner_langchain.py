import asyncio
from typing import Dict, List, Any
from pydantic import BaseModel, Field
from rich.prompt import Prompt

from langchain_openai import ChatOpenAI
from langchain.agents import Tool, AgentType, initialize_agent
from water import Flow, create_task

# === Pydantic Schemas for Structured Output ===
class Lesson(BaseModel):
    title: str = Field(description="The title of the lesson")
    description: str = Field(description="A brief description of what the lesson covers")

class CourseOutlineSchema(BaseModel):
    lessons: List[Lesson] = Field(description="A list of lessons for the course outline")

# === 1. LLM ===
llm = ChatOpenAI(model_name="gpt-4o", temperature=0)

# === 2. Tool: Course Outliner ===
def course_outline_tool(course: str) -> str:
    prompt = f"""You are an expert curriculum designer. Create a structured course outline with 5-8 lessons for the course: '{course}'. Each lesson should have a title and a short description."""
    
    structured_llm = llm.with_structured_output(CourseOutlineSchema)
    response_model = structured_llm.invoke(prompt)
    return response_model.model_dump_json()


course_outliner_tool = Tool.from_function(
    name="CourseOutliner",
    description="Creates a lesson-by-lesson course outline. Input: course name.",
    func=course_outline_tool
)

# === 3. Tool: Lesson Expander ===
def expand_lesson_tool(input: str) -> str:
    """
    Input format: 'lesson: <lesson>, course: <course>'
    """
    try:
        parts = input.split("lesson:")[1].split(", course:")
        lesson = parts[0].strip()
        course = parts[1].strip()
    except:
        return "Invalid input format. Use: lesson: <lesson>, course: <course>"

    prompt = f"""
You are an educational expert. Expand the lesson **{lesson}** from the course **{course}**.

Include:
1. **Learning Objectives**
2. **Key Concepts**
3. **Lesson Outline**
4. **Suggested Examples or Tools**

Respond in Markdown format.
"""
    return llm.invoke(prompt).content

lesson_expander_tool = Tool.from_function(
    name="LessonExpander",
    description="Expands a lesson into full detail. Input: 'lesson: <lesson>, course: <course>'",
    func=expand_lesson_tool
)

# === 4. Tool: Capstone Project Suggester ===
def capstone_project_tool(course: str) -> str:
    prompt = f"""
You are a capstone mentor. Suggest 2–3 final projects for the course **{course}**.

For each project include:
- Title
- Description
- Required skills/tools
- Expected outcome

Respond in Markdown.
"""
    return llm.invoke(prompt).content

capstone_tool = Tool.from_function(
    name="ProjectSuggester",
    description="Suggests final capstone projects for a course.",
    func=capstone_project_tool
)

# === 5. Agents ===
# course_planner_agent = initialize_agent(
#     tools=[course_outliner_tool],
#     llm=llm,
#     agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
#     verbose=True,
# )

# lesson_agent = initialize_agent(
#     tools=[lesson_expander_tool],
#     llm=llm,
#     agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
#     verbose=True,
# )

project_agent = initialize_agent(
    tools=[capstone_tool],
    llm=llm,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
)

# === 6. Pydantic Models ===
class CourseInput(BaseModel):
    topic: str

class CourseOutline(BaseModel):
    outline: str

class ExpandedLessons(BaseModel):
    content: Dict[str, str]

class ProjectSuggestions(BaseModel):
    projects_md: str
    outline: Any | None = None  # include previous task outputs
    expand_lessons: Any | None = None

# === 7. Task Functions ===
def run_course_outline(params: Dict[str, Any], context) -> CourseOutline:
    course = params["input_data"]["topic"]
    # result = course_planner_agent.run(course)
    result = course_outline_tool(course)
    return {"outline": result, "topic": course}

import json

def run_lesson_expansion(params: Dict[str, Any], context) -> ExpandedLessons:
    course = params["input_data"]["topic"]
    outline_json = params["input_data"]["outline"]

    try:
        # outline_json is now expected to be a string like '{"lessons": [{"title": "...", "description": "..."}, ...]}'
        parsed_outline = json.loads(outline_json)
        lessons = parsed_outline.get("lessons") # Get the list of lesson dicts

        if lessons is None:
            print(f"ERROR: 'lessons' key not found in parsed_outline. Received: {outline_json}")
            return {"content": {"error": "Invalid structure: 'lessons' key missing"}, "topic": course}
        if not isinstance(lessons, list):
            print(f"ERROR: 'lessons' key is not a list in parsed_outline. Received: {outline_json}")
            return {"content": {"error": "Invalid structure: 'lessons' is not a list"}, "topic": course}
        # It's okay if lessons is an empty list, the loop below will simply not run.

    except json.JSONDecodeError as e:
        print(f"ERROR: JSONDecodeError in run_lesson_expansion: {e}. Received outline_json: {outline_json}")
        return {"content": {"error": "Invalid JSON format in course outline"}, "topic": course}

    expanded = {}
    for lesson in lessons:
        lesson_title = lesson["title"]
        prompt = f"lesson: {lesson_title}, course: {course}"
        result = lesson_expander_tool(prompt)
        expanded[lesson_title] = result

    return {"content": expanded, "topic": course}

def run_project_suggestions(params: Dict[str, Any], context) -> ProjectSuggestions:
    all_outputs = context.get_all_task_outputs()
    topic = params["input_data"]["topic"]
    projects_md = project_agent.run(topic)
    outline_output = all_outputs.get("outline")
    expand_output = all_outputs.get("expand_lessons")
    return {
        "projects_md": projects_md,
        "outline": outline_output,
        "expand_lessons": expand_output,
    }

# === 8. Tasks ===
outline_task = create_task(
    id="outline",
    description="Generate a course outline.",
    execute=run_course_outline,
    input_schema=CourseInput,
    output_schema=CourseOutline
)

expand_task = create_task(
    id="expand_lessons",
    description="Expand all lessons from the outline.",
    execute=run_lesson_expansion,
    input_schema=CourseInput,
    output_schema=ExpandedLessons
)

project_task = create_task(
    id="projects",
    description="Suggest final capstone projects.",
    execute=run_project_suggestions,
    input_schema=CourseInput,
    output_schema=ProjectSuggestions
)

# === 9. Flow ===
course_flow = Flow(id="course_planner_flow", description="Course Planning with LangChain & Water")
course_flow.then(outline_task).then(expand_task).then(project_task).register()

# === 10. Run Main ===
async def main():
    topic = Prompt.ask(
        "[bold]Enter a course topic[/bold] (e.g., 'Data Structures for Beginners')",
    )
    print(f"\n🧠 Planning Course: {topic}\n" + "=" * 80)

    result = await course_flow.run({"topic": topic})

    # ---- Create Markdown Summary ----
    try:
        md_lines = [f"# Course Plan: {topic}\n"]
        # Course Outline
        md_lines.append("## Course Outline\n")
        outline_output = result.get("outline") or {}
        outline_json = outline_output.get("outline") if isinstance(outline_output, dict) else outline_output
        if outline_json:
            try:
                outline_parsed = json.loads(outline_json)
                for lesson in outline_parsed.get("lessons", []):
                    title = lesson.get("title", "Untitled Lesson")
                    desc = lesson.get("description", "")
                    md_lines.append(f"### {title}\n")
                    md_lines.append(f"{desc}\n")
            except Exception:
                md_lines.append(str(outline_json) + "\n")

        # Expanded Lessons
        md_lines.append("\n## Expanded Lessons\n")
        lessons_output = result.get("expand_lessons", {}).get("content", {})
        for lesson_title, lesson_content in lessons_output.items():
            md_lines.append(f"### {lesson_title}\n")
            md_lines.append(f"{lesson_content}\n")

        # Capstone Projects
        md_lines.append("\n## Capstone Project Suggestions\n")
        projects_md = result.get("projects", {}).get("projects_md") or result.get("projects_md", "")
        md_lines.append(projects_md + "\n")

        # Write to file
        md_path = "course_plan.md"
        with open(md_path, "w", encoding="utf-8") as md_file:
            md_file.write("\n".join(md_lines))
        print(f"\n✅ Course plan saved to {md_path}")
    except Exception as e:
        print(f"⚠️  Failed to write markdown file: {e}")
    # print(result)

    # print("\n📘 Course Outline\n" + "-" * 80)
    # print(result["projects_md"])

    # print("\n📚 Expanded Lessons\n" + "-" * 80)
    # for lesson, content in result["expand_lessons"]["content"].items():
    #     print(f"\n## {lesson}\n")
    #     print(content)

    # print("\n🎓 Capstone Projects\n" + "-" * 80)
    # print(result["projects"]["projects_md"])


if __name__ == "__main__":
    asyncio.run(main())
