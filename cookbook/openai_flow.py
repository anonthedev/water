"""
Customer support ticket router using OpenAI directly with Water.

Demonstrates branching and parallel execution:
1. A classifier task categorizes the support ticket
2. Branching routes to the appropriate specialist handler
3. Each handler uses OpenAI to generate a tailored response

pip install openai water-ai
"""

import asyncio
from typing import Any, Dict

from openai import OpenAI
from pydantic import BaseModel

from water import Flow, create_task


client = OpenAI()
MODEL = "gpt-4o-mini"


# --- Pydantic Schemas ---

class TicketInput(BaseModel):
    message: str
    customer_name: str

class ClassifiedTicket(BaseModel):
    message: str
    customer_name: str
    category: str
    urgency: str

class TicketResponse(BaseModel):
    reply: str
    category: str
    actions: str


# --- Task Execution Functions ---

def classify_ticket(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Classify the incoming support ticket by category and urgency."""
    message = params["input_data"]["message"]
    customer_name = params["input_data"]["customer_name"]

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a support ticket classifier. Categorize the ticket into exactly "
                    "one of: 'billing', 'technical', 'general'. Also rate urgency as 'low', "
                    "'medium', or 'high'. Respond in the format:\n"
                    "category: <category>\nurgency: <urgency>"
                ),
            },
            {"role": "user", "content": message},
        ],
    )

    text = response.choices[0].message.content.strip().lower()
    category = "general"
    urgency = "medium"

    for line in text.split("\n"):
        if line.startswith("category:"):
            cat = line.split(":", 1)[1].strip()
            if cat in ("billing", "technical", "general"):
                category = cat
        elif line.startswith("urgency:"):
            urg = line.split(":", 1)[1].strip()
            if urg in ("low", "medium", "high"):
                urgency = urg

    return {
        "message": message,
        "customer_name": customer_name,
        "category": category,
        "urgency": urgency,
    }


def handle_billing(params: Dict[str, Any], context) -> Dict[str, str]:
    """Handle billing-related support tickets."""
    data = params["input_data"]

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a billing support specialist. Be empathetic and helpful. "
                    "Provide clear steps to resolve billing issues. Address the customer by name."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Customer: {data['customer_name']}\n"
                    f"Urgency: {data['urgency']}\n"
                    f"Message: {data['message']}"
                ),
            },
        ],
    )

    return {
        "reply": response.choices[0].message.content,
        "category": "billing",
        "actions": "Flagged for billing team review",
    }


def handle_technical(params: Dict[str, Any], context) -> Dict[str, str]:
    """Handle technical support tickets."""
    data = params["input_data"]

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a technical support engineer. Provide clear troubleshooting steps. "
                    "Be precise and technical but accessible. Address the customer by name."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Customer: {data['customer_name']}\n"
                    f"Urgency: {data['urgency']}\n"
                    f"Message: {data['message']}"
                ),
            },
        ],
    )

    return {
        "reply": response.choices[0].message.content,
        "category": "technical",
        "actions": "Created troubleshooting ticket",
    }


def handle_general(params: Dict[str, Any], context) -> Dict[str, str]:
    """Handle general inquiry tickets."""
    data = params["input_data"]

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a friendly customer support agent. Be warm and helpful. "
                    "Answer questions clearly and offer further assistance. Address the customer by name."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Customer: {data['customer_name']}\n"
                    f"Urgency: {data['urgency']}\n"
                    f"Message: {data['message']}"
                ),
            },
        ],
    )

    return {
        "reply": response.choices[0].message.content,
        "category": "general",
        "actions": "No further action required",
    }


# --- Water Tasks ---

classify_task = create_task(
    id="classify_ticket",
    description="Classify support ticket by category and urgency using OpenAI",
    execute=classify_ticket,
    input_schema=TicketInput,
    output_schema=ClassifiedTicket,
)

billing_task = create_task(
    id="handle_billing",
    description="Generate billing support response using OpenAI",
    execute=handle_billing,
    input_schema=ClassifiedTicket,
    output_schema=TicketResponse,
)

technical_task = create_task(
    id="handle_technical",
    description="Generate technical support response using OpenAI",
    execute=handle_technical,
    input_schema=ClassifiedTicket,
    output_schema=TicketResponse,
)

general_task = create_task(
    id="handle_general",
    description="Generate general support response using OpenAI",
    execute=handle_general,
    input_schema=ClassifiedTicket,
    output_schema=TicketResponse,
)


# --- Water Flow ---

support_flow = Flow(
    id="customer_support_flow",
    description="Classify and route support tickets to specialist handlers using OpenAI",
)
support_flow.then(classify_task).branch([
    (lambda data: data.get("category") == "billing", billing_task),
    (lambda data: data.get("category") == "technical", technical_task),
    (lambda data: data.get("category") == "general", general_task),
]).register()


async def main():
    name = input("Customer name: ").strip() or "Alice"
    message = input("Support message: ").strip() or "I was charged twice for my subscription this month"

    print(f"\nProcessing support ticket from {name}...\n")

    result = await support_flow.run({"message": message, "customer_name": name})

    print(f"Category: {result['category']}")
    print(f"Actions: {result['actions']}")
    print(f"\nResponse:\n{result['reply']}")


if __name__ == "__main__":
    asyncio.run(main())
