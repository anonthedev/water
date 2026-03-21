"""
Prompt Templating Engine for Water.

Provides a lightweight template system for managing and composing LLM prompts
without requiring Jinja2 or any external templating dependency. Uses the
``{{variable}}`` syntax for variable interpolation and supports default values,
template composition, and validation.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any

# Escape sequence for literal braces: \{{ and \}}
_ESCAPED_OPEN = "\\{{"
_ESCAPED_CLOSE = "\\}}"
# Sentinel replacements used during rendering to avoid interference with variable substitution
_OPEN_SENTINEL = "\x00OPEN_BRACE\x00"
_CLOSE_SENTINEL = "\x00CLOSE_BRACE\x00"

# Pattern that matches {{variable_name}} with optional whitespace inside braces
_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class PromptTemplateError(Exception):
    """Raised when a prompt template operation fails."""


class PromptTemplate:
    """
    A simple prompt template using ``{{variable}}`` placeholders.

    Args:
        template: The template string with ``{{var}}`` placeholders.
        defaults: Optional mapping of variable names to default values.
    """

    def __init__(self, template: str, defaults: Optional[Dict[str, str]] = None):
        self.template = template
        self.defaults: Dict[str, str] = defaults or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, **kwargs: Any) -> str:
        """Render the template by substituting variables.

        Variables are resolved in this order:
        1. Explicit ``kwargs`` passed to this call.
        2. ``defaults`` provided at construction time.

        Raises:
            PromptTemplateError: If any placeholder has no value after
                applying defaults and kwargs.
        """
        variables: Dict[str, str] = {**self.defaults, **kwargs}

        missing = self.validate(list(variables.keys()))
        if missing:
            raise PromptTemplateError(
                f"Missing variables for template rendering: {missing}"
            )

        # Protect escaped braces from variable substitution
        result = self.template.replace(_ESCAPED_OPEN, _OPEN_SENTINEL)
        result = result.replace(_ESCAPED_CLOSE, _CLOSE_SENTINEL)

        def _replacer(match: re.Match) -> str:
            name = match.group(1)
            return str(variables[name])

        result = _VAR_PATTERN.sub(_replacer, result)

        # Restore escaped braces as literal double-brace characters
        result = result.replace(_OPEN_SENTINEL, "{{")
        result = result.replace(_CLOSE_SENTINEL, "}}")
        return result

    def get_variables(self) -> List[str]:
        """Return a sorted, deduplicated list of variable names in the template."""
        # Strip escaped braces before scanning for real variables
        cleaned = self.template.replace(_ESCAPED_OPEN, "").replace(_ESCAPED_CLOSE, "")
        return sorted(set(_VAR_PATTERN.findall(cleaned)))

    def validate(self, available_vars: List[str]) -> List[str]:
        """Return a list of required variables **not** present in *available_vars*.

        Args:
            available_vars: Variable names that the caller can supply.

        Returns:
            Sorted list of missing variable names (empty if all are covered).
        """
        available = set(available_vars)
        required = set(self.get_variables())
        return sorted(required - available)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"PromptTemplate(variables={self.get_variables()}, "
            f"defaults={list(self.defaults.keys())})"
        )


class PromptLibrary:
    """A named registry of :class:`PromptTemplate` instances.

    Supports registration, retrieval, rendering, and composition of
    templates by name.
    """

    def __init__(self) -> None:
        self._templates: Dict[str, PromptTemplate] = {}

    # ------------------------------------------------------------------
    # Registration & retrieval
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        template: str,
        defaults: Optional[Dict[str, str]] = None,
    ) -> None:
        """Register a template string under *name*.

        Raises:
            PromptTemplateError: If *name* is already registered.
        """
        if name in self._templates:
            raise PromptTemplateError(
                f"Template '{name}' is already registered"
            )
        self._templates[name] = PromptTemplate(template, defaults)

    def get(self, name: str) -> PromptTemplate:
        """Retrieve a registered :class:`PromptTemplate` by *name*.

        Raises:
            PromptTemplateError: If no template with *name* exists.
        """
        if name not in self._templates:
            raise PromptTemplateError(f"Template '{name}' not found")
        return self._templates[name]

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a named template with the supplied variables.

        Args:
            template_name: The registered name of the template to render.
            **kwargs: Variable values to pass to the template.
        """
        return self.get(template_name).render(**kwargs)

    def compose(self, *names: str, separator: str = "\n\n") -> PromptTemplate:
        """Compose multiple named templates into a single :class:`PromptTemplate`.

        The templates are joined using *separator*. Defaults from all
        constituent templates are merged (later templates take precedence
        for overlapping keys).

        Args:
            *names: Names of templates to compose, in order.
            separator: String placed between each template section.

        Returns:
            A new :class:`PromptTemplate` combining all named templates.

        Raises:
            PromptTemplateError: If any named template is not found.
        """
        parts: List[str] = []
        merged_defaults: Dict[str, str] = {}
        for name in names:
            tpl = self.get(name)
            parts.append(tpl.template)
            merged_defaults.update(tpl.defaults)
        return PromptTemplate(separator.join(parts), merged_defaults)

    def list_templates(self) -> List[str]:
        """Return a sorted list of registered template names."""
        return sorted(self._templates.keys())
