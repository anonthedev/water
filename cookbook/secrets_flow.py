"""
Secrets Flow
=============

Demonstrates secure injection of API keys and credentials into tasks using
the Water secrets manager.  Secrets are automatically masked in string
representations (``str()``, ``repr()``, ``print()``), preventing accidental
leakage in logs and debug output.

Tasks access secrets via ``context.get_service('secrets')``.
"""

import asyncio
from pydantic import BaseModel
from water import create_task, Flow, SecretsManager


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class QueryInput(BaseModel):
    query: str


class APIResponse(BaseModel):
    answer: str
    source: str


class FinalOutput(BaseModel):
    answer: str
    source: str
    summary: str


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@create_task(
    id="call_external_api",
    description="Call an external API using a secret API key",
    input_schema=QueryInput,
    output_schema=APIResponse,
)
async def call_external_api(input_data, context):
    secrets = context.get_service("secrets")
    api_key = secrets.reveal("external_api_key")

    # Demonstrate that printing the SecretValue is safe
    secret_obj = secrets.get("external_api_key")
    print(f"[LOG] Using API key: {secret_obj}")  # prints: [LOG] Using API key: ***

    # In a real application you would use the key in an HTTP request:
    # response = await httpx.AsyncClient().get(
    #     "https://api.example.com/search",
    #     headers={"Authorization": f"Bearer {api_key}"},
    #     params={"q": input_data["query"]},
    # )
    # Simulated response:
    return {
        "answer": f"Result for '{input_data['query']}'",
        "source": "example-api",
    }


@create_task(
    id="summarize",
    description="Summarize the API response using a second service",
    input_schema=APIResponse,
    output_schema=FinalOutput,
)
async def summarize(input_data, context):
    secrets = context.get_service("secrets")
    llm_key = secrets.reveal("llm_api_key")

    # Again, the key is masked if accidentally logged
    print(f"[LOG] LLM key object: {secrets.get('llm_api_key')}")  # prints: ***

    # Simulated summarization
    return {
        **input_data,
        "summary": f"Summary of: {input_data['answer']}",
    }


# ---------------------------------------------------------------------------
# Flow definition
# ---------------------------------------------------------------------------

secrets = SecretsManager()
secrets.set("external_api_key", "sk-ext-real-key-do-not-log")
secrets.set("llm_api_key", "sk-llm-real-key-do-not-log")

flow = Flow(id="secrets_demo", description="API flow with secret key injection")
flow.secrets = secrets
flow.then(call_external_api).then(summarize).register()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

async def main():
    print("=== Secrets are masked in all string output ===")
    print(f"external_api_key as string: {secrets.get('external_api_key')}")
    print(f"Registered secret names: {secrets.list_names()}")
    print()

    result = await flow.run({"query": "What is Water framework?"})
    print()
    print("Final result:", result)


if __name__ == "__main__":
    asyncio.run(main())
