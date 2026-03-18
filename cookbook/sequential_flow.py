"""
Sequential Flow Example: User Registration Pipeline

This example demonstrates a sequential flow where each step must complete 
before the next can begin. Shows how .then() creates clear dependencies and 
how context preserves data across the pipeline.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import uuid

# Data schemas
class UserRequest(BaseModel):
    email: str
    password: str
    first_name: str

class ValidationResult(BaseModel):
    email: str
    first_name: str
    is_valid: bool
    errors: list

class AccountResult(BaseModel):
    email: str
    first_name: str
    user_id: str
    account_created: bool

class ProfileResult(BaseModel):
    user_id: str
    profile_id: str
    profile_created: bool

class RegistrationSummary(BaseModel):
    user_id: str
    profile_id: str
    email: str
    registration_complete: bool
    total_time: float

# Step 1: Validate Input
def validate_input(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Validate user registration data."""
    request = params["input_data"]
    errors = []
    
    if "@" not in request["email"]:
        errors.append("Invalid email")
    if len(request["password"]) < 6:
        errors.append("Password too short")
    if not request["first_name"]:
        errors.append("Name required")
    
    return {
        "email": request["email"],
        "first_name": request["first_name"],
        "is_valid": len(errors) == 0,
        "errors": errors
    }

# Step 2: Create Account
def create_account(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Create user account - depends on successful validation."""
    current_data = params["input_data"]
    
    if not current_data["is_valid"]:
        return {
            "email": current_data["email"],
            "first_name": current_data["first_name"],
            "user_id": "",
            "account_created": False
        }
    
    # Generate user ID
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    
    return {
        "email": current_data["email"],
        "first_name": current_data["first_name"],
        "user_id": user_id,
        "account_created": True
    }

# Step 3: Setup Profile
def setup_profile(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Setup user profile - depends on account creation."""
    current_data = params["input_data"]
    
    # Access account creation results from context
    account = context.get_task_output("account")
    
    if not current_data["account_created"]:
        return {
            "user_id": current_data["user_id"],
            "profile_id": "",
            "profile_created": False
        }
    
    # Generate profile ID
    profile_id = f"profile_{uuid.uuid4().hex[:8]}"
    
    return {
        "user_id": current_data["user_id"],
        "profile_id": profile_id,
        "profile_created": True
    }

# Step 4: Complete Registration
def complete_registration(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Complete registration - depends on all previous steps."""
    current_data = params["input_data"]
    
    # Access all previous step results from context
    validation = context.get_task_output("validate")
    
    return {
        "user_id": current_data["user_id"],
        "profile_id": current_data["profile_id"],
        "email": validation["email"],
        "registration_complete": current_data["profile_created"]
    }

# Create tasks
validate_task = create_task(
    id="validate",
    description="Validate registration input",
    input_schema=UserRequest,
    output_schema=ValidationResult,
    execute=validate_input
)

account_task = create_task(
    id="account",
    description="Create user account",
    input_schema=ValidationResult,
    output_schema=AccountResult,
    execute=create_account
)

profile_task = create_task(
    id="profile",
    description="Setup user profile",
    input_schema=AccountResult,
    output_schema=ProfileResult,
    execute=setup_profile
)

complete_task = create_task(
    id="complete",
    description="Complete registration",
    input_schema=ProfileResult,
    output_schema=RegistrationSummary,
    execute=complete_registration
)

# Sequential registration flow - each step depends on the previous
registration_flow = Flow(id="user_registration", description="Sequential user registration pipeline")
registration_flow.then(validate_task)\
    .then(account_task)\
    .then(profile_task)\
    .then(complete_task)\
    .register()

async def main():
    """Run the sequential registration example."""
    
    user_request = {
        "email": "manthan.gupta@water.ai",
        "password": "SecurePass123",
        "first_name": "Manthan"
    }
    
    try:
        result = await registration_flow.run(user_request)
        
        if result["registration_complete"]:
            print(result)
        else:
            print("FAILED - Registration incomplete")
        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")

if __name__ == "__main__":
    asyncio.run(main()) 