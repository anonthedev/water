"""
Branched Flow Example: Conditional Notification Flow

This example demonstrates a branched flow where notifications are sent
based on user preferences. Shows how .branch() executes only the first 
matching condition, even when multiple conditions would match.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio

# Data schemas
class UserPreferences(BaseModel):
    user_id: str
    email_enabled: bool
    sms_enabled: bool
    whatsapp_enabled: bool

class NotificationSent(BaseModel):
    user_id: str
    channel: str
    sent: bool

# Notification tasks
def send_email(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Send email notification."""
    user = params["input_data"]
    return {
        "user_id": user["user_id"],
        "channel": "email",
        "sent": True
    }

def send_sms(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Send SMS notification."""
    user = params["input_data"]
    return {
        "user_id": user["user_id"],
        "channel": "sms", 
        "sent": True
    }

def send_whatsapp(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Send WhatsApp notification."""
    user = params["input_data"]
    return {
        "user_id": user["user_id"],
        "channel": "whatsapp",
        "sent": True
    }

# Create tasks
email_task = create_task(
    id="email",
    description="Send email",
    input_schema=UserPreferences,
    output_schema=NotificationSent,
    execute=send_email
)

sms_task = create_task(
    id="sms",
    description="Send SMS",
    input_schema=UserPreferences,
    output_schema=NotificationSent,
    execute=send_sms
)

whatsapp_task = create_task(
    id="whatsapp",
    description="Send WhatsApp",
    input_schema=UserPreferences,
    output_schema=NotificationSent,
    execute=send_whatsapp
)

# Branched notification flow
notification_flow = Flow(id="conditional_notifications", description="Conditional notification flow")
notification_flow.branch([
    (lambda data: data.get("email_enabled", False), email_task),
    (lambda data: data.get("sms_enabled", False), sms_task),
    (lambda data: data.get("whatsapp_enabled", False), whatsapp_task)
]).register()

async def main():
    """Run the branched notification flow example."""
    
    user = {
        "user_id": "user_001",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": False
    }
    
    print(f"User preferences: email={user['email_enabled']}, sms={user['sms_enabled']}, whatsapp={user['whatsapp_enabled']}")
    
    try:
        result = await notification_flow.run(user)
        print(f"Notification sent via: {result['channel']}")
        print(f"First matching condition executed (email has priority)")
        
    except Exception as e:
        print(f"ERROR - {e}")

if __name__ == "__main__":
    asyncio.run(main()) 