"""
Parallel Flow Example: Send Notification Flow

This example demonstrates a parallel flow where multiple welcome notifications
are sent simultaneously to a newly registered user. Shows how .parallel() executes
independent tasks concurrently for improved performance.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import uuid

# Data schemas
class UserData(BaseModel):
    user_id: str
    email: str
    phone: str
    first_name: str

class NotificationResult(BaseModel):
    channel: str
    user_id: str
    message_id: str
    sent: bool
    delivery_time: float

class ParallelResults(BaseModel):
    email: NotificationResult
    sms: NotificationResult
    whatsapp: NotificationResult

class Summary(BaseModel):
    user_id: str
    notifications_sent: int
    total_time: float
    success: bool

# Parallel Task 1: Send Email
def send_email(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Send welcome email to the user."""
    user = params["input_data"]
    
    return {
        "channel": "email",
        "user_id": user["user_id"],
        "message_id": f"email_{uuid.uuid4().hex[:8]}",
        "sent": True,
        "delivery_time": 1.2
    }

# Parallel Task 2: Send SMS
def send_sms(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Send welcome SMS to the user."""
    user = params["input_data"]
    
    return {
        "channel": "sms",
        "user_id": user["user_id"],
        "message_id": f"sms_{uuid.uuid4().hex[:8]}",
        "sent": True,
        "delivery_time": 0.8
    }

# Parallel Task 3: Send WhatsApp
def send_whatsapp(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Send welcome WhatsApp message to the user."""
    user = params["input_data"]
    
    return {
        "channel": "whatsapp",
        "user_id": user["user_id"],
        "message_id": f"whatsapp_{uuid.uuid4().hex[:8]}",
        "sent": True,
        "delivery_time": 1.5
    }

# Aggregation Task: Summarize Results
def summarize_results(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Aggregate results from all parallel notification tasks."""
    results = params["input_data"]
    
    # Count successful notifications
    sent_count = sum(1 for result in results.values() if result["sent"])
    
    # Get maximum time (since they ran in parallel)
    max_time = max(result["delivery_time"] for result in results.values())
    
    return {
        "user_id": list(results.values())[0]["user_id"],
        "notifications_sent": sent_count,
        "total_time": max_time,
        "success": sent_count == 3
    }

# Create tasks
email_task = create_task(
    id="email",
    description="Send email notification",
    input_schema=UserData,
    output_schema=NotificationResult,
    execute=send_email
)

sms_task = create_task(
    id="sms", 
    description="Send SMS notification",
    input_schema=UserData,
    output_schema=NotificationResult,
    execute=send_sms
)

whatsapp_task = create_task(
    id="whatsapp",
    description="Send WhatsApp notification", 
    input_schema=UserData,
    output_schema=NotificationResult,
    execute=send_whatsapp
)

summary_task = create_task(
    id="summary",
    description="Summarize notification results",
    input_schema=ParallelResults,
    output_schema=Summary,
    execute=summarize_results
)

# Parallel send notification flow
send_notification_flow = Flow(id="send_notifications", description="Parallel send notification flow")
send_notification_flow.parallel([
    email_task,
    sms_task, 
    whatsapp_task
]).then(summary_task).register()

async def main():
    """Run the send notification flow example."""
    
    user = {
        "user_id": "user_abc123",
        "email": "manthan.gupta@water.ai",
        "phone": "+1234567890",
        "first_name": "Manthan"
    }
    
    try:
        result = await send_notification_flow.run(user)
        print(result)
        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")

if __name__ == "__main__":
    asyncio.run(main()) 