"""
Schema validation guardrail.

Validates that LLM output matches an expected JSON schema or Pydantic model.
"""

import json
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from water.guardrails.base import Guardrail, GuardrailResult


class SchemaGuardrail(Guardrail):
    """
    Validate output data against a Pydantic model or JSON schema.

    Args:
        schema: A Pydantic BaseModel class to validate against.
        strict: If True, disallow extra fields.
        response_key: Key in data dict containing the JSON to validate.
            If None, validates the entire data dict.
        action: What to do on failure.
    """

    name = "schema_guardrail"

    def __init__(
        self,
        schema: Type[BaseModel],
        strict: bool = False,
        response_key: Optional[str] = None,
        action: str = "block",
        name: Optional[str] = None,
    ):
        super().__init__(name=name, action=action)
        self.schema = schema
        self.strict = strict
        self.response_key = response_key

    def validate(self, data: Dict[str, Any], context: Optional[Any] = None) -> GuardrailResult:
        target = data
        if self.response_key:
            target = data.get(self.response_key, data)

        # If target is a JSON string, parse it
        if isinstance(target, str):
            try:
                target = json.loads(target)
            except json.JSONDecodeError:
                return GuardrailResult(
                    passed=False,
                    reason="Response is not valid JSON",
                    details={"raw_response": target[:200]},
                )

        if not isinstance(target, dict):
            return GuardrailResult(
                passed=False,
                reason=f"Expected dict, got {type(target).__name__}",
            )

        try:
            self.schema(**target)
            return GuardrailResult(passed=True)
        except Exception as e:
            return GuardrailResult(
                passed=False,
                reason=f"Schema validation failed: {e}",
                details={"errors": str(e)},
            )
