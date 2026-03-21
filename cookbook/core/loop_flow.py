"""
Loop Flow Example: Notification Retry with Backoff

This example demonstrates a loop flow that retries a flaky notification 
service until success or max attempts reached. Shows how .loop() continues
execution based on conditions and tracks state between iterations.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import random
import time

# Data schemas
class RetryState(BaseModel):
    user_id: str
    message: str
    max_attempts: int = 3
    attempt: int = 0
    success: bool = False
    error: str = ""
    should_retry: bool = True

# Retry task (simulates flaky service)
def attempt_notification(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Attempt to send notification (simulates 70% failure rate)."""
    data = params["input_data"]
    
    # Increment attempt counter
    current_attempt = data.get("attempt", 0) + 1
    
    # Add backoff delay for retries
    if current_attempt > 1:
        time.sleep(0.5 * current_attempt)
    
    # Simulate flaky service (60% success rate)
    success = random.random() < 0.6
    
    result = {
        "user_id": data["user_id"],
        "message": data["message"],
        "max_attempts": data["max_attempts"],
        "attempt": current_attempt,
        "success": success,
        "error": "" if success else f"Network timeout on attempt {current_attempt}",
        "should_retry": not success and current_attempt < data["max_attempts"]
    }
    
    return result

# Create task
notification_task = create_task(
    id="attempt_notification",
    description="Attempt notification with retry",
    input_schema=RetryState,
    output_schema=RetryState,
    execute=attempt_notification
)

# Loop flow with retry logic
retry_flow = Flow(id="notification_retry", description="Notification retry flow")
retry_flow.loop(
    task=notification_task,
    condition=lambda result: result.get("should_retry", False)
).register()

async def main():
    """Run the loop retry flow example."""
    
    request = {
        "user_id": "user_001",
        "message": "Welcome to Water Framework!",
        "max_attempts": 3,
        "attempt": 0,
        "success": False,
        "error": "",
        "should_retry": True
    }
    
    try:
        result = await retry_flow.run(request)
        
        if result.get("success"):
            print(f"Notification sent successfully on attempt {result['attempt']}")
        else:
            print(f"Notification failed after {result['attempt']} attempts")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 