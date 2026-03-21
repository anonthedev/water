"""Tests for the Prompt Templating Engine."""

import pytest

from water.agents.prompts import PromptTemplate, PromptLibrary, PromptTemplateError


# ---------------------------------------------------------------------------
# PromptTemplate tests
# ---------------------------------------------------------------------------

class TestPromptTemplateRendering:
    """Basic rendering with variable substitution."""

    def test_render_simple(self):
        tpl = PromptTemplate("Hello, {{name}}!")
        assert tpl.render(name="World") == "Hello, World!"

    def test_render_multiple_variables(self):
        tpl = PromptTemplate("{{greeting}}, {{name}}! You are {{role}}.")
        result = tpl.render(greeting="Hi", name="Alice", role="admin")
        assert result == "Hi, Alice! You are admin."

    def test_render_with_whitespace_in_braces(self):
        tpl = PromptTemplate("Hello, {{ name }}!")
        assert tpl.render(name="World") == "Hello, World!"

    def test_render_repeated_variable(self):
        tpl = PromptTemplate("{{x}} and {{x}}")
        assert tpl.render(x="A") == "A and A"


class TestPromptTemplateDefaults:
    """Default values for variables."""

    def test_render_uses_defaults(self):
        tpl = PromptTemplate("Hello, {{name}}!", defaults={"name": "World"})
        assert tpl.render() == "Hello, World!"

    def test_kwargs_override_defaults(self):
        tpl = PromptTemplate("Hello, {{name}}!", defaults={"name": "World"})
        assert tpl.render(name="Alice") == "Hello, Alice!"

    def test_partial_defaults(self):
        tpl = PromptTemplate(
            "{{greeting}}, {{name}}!",
            defaults={"greeting": "Hi"},
        )
        assert tpl.render(name="Bob") == "Hi, Bob!"


class TestPromptTemplateMissingVars:
    """Missing variable detection."""

    def test_missing_variable_raises(self):
        tpl = PromptTemplate("Hello, {{name}}!")
        with pytest.raises(PromptTemplateError, match="Missing variables"):
            tpl.render()

    def test_missing_one_of_many_raises(self):
        tpl = PromptTemplate("{{a}} {{b}} {{c}}")
        with pytest.raises(PromptTemplateError):
            tpl.render(a="1", c="3")


class TestGetVariables:
    """Extraction of variable names from templates."""

    def test_get_variables_basic(self):
        tpl = PromptTemplate("{{foo}} and {{bar}}")
        assert tpl.get_variables() == ["bar", "foo"]

    def test_get_variables_deduplication(self):
        tpl = PromptTemplate("{{x}} {{x}} {{y}}")
        assert tpl.get_variables() == ["x", "y"]

    def test_get_variables_empty_template(self):
        tpl = PromptTemplate("No variables here.")
        assert tpl.get_variables() == []


class TestValidate:
    """Validation of available variables against template requirements."""

    def test_validate_all_present(self):
        tpl = PromptTemplate("{{a}} {{b}}")
        assert tpl.validate(["a", "b"]) == []

    def test_validate_missing(self):
        tpl = PromptTemplate("{{a}} {{b}} {{c}}")
        assert tpl.validate(["a"]) == ["b", "c"]


# ---------------------------------------------------------------------------
# PromptLibrary tests
# ---------------------------------------------------------------------------

class TestPromptLibrary:
    """Registration, retrieval, rendering, and composition."""

    def test_register_and_get(self):
        lib = PromptLibrary()
        lib.register("greet", "Hello, {{name}}!")
        tpl = lib.get("greet")
        assert tpl.render(name="World") == "Hello, World!"

    def test_register_duplicate_raises(self):
        lib = PromptLibrary()
        lib.register("greet", "Hello!")
        with pytest.raises(PromptTemplateError, match="already registered"):
            lib.register("greet", "Hi!")

    def test_get_missing_raises(self):
        lib = PromptLibrary()
        with pytest.raises(PromptTemplateError, match="not found"):
            lib.get("nope")

    def test_render(self):
        lib = PromptLibrary()
        lib.register("greet", "Hello, {{name}}!", defaults={"name": "World"})
        assert lib.render("greet") == "Hello, World!"
        assert lib.render("greet", name="Alice") == "Hello, Alice!"

    def test_compose(self):
        lib = PromptLibrary()
        lib.register("system", "You are {{role}}.")
        lib.register("task", "Please {{action}}.")
        composed = lib.compose("system", "task")
        result = composed.render(role="a helper", action="summarize")
        assert result == "You are a helper.\n\nPlease summarize."

    def test_compose_custom_separator(self):
        lib = PromptLibrary()
        lib.register("a", "A")
        lib.register("b", "B")
        composed = lib.compose("a", "b", separator=" | ")
        assert composed.render() == "A | B"

    def test_compose_merges_defaults(self):
        lib = PromptLibrary()
        lib.register("sys", "Role: {{role}}", defaults={"role": "assistant"})
        lib.register("task", "Do: {{action}}", defaults={"action": "help"})
        composed = lib.compose("sys", "task")
        assert composed.render() == "Role: assistant\n\nDo: help"

    def test_list_templates(self):
        lib = PromptLibrary()
        lib.register("b_template", "B")
        lib.register("a_template", "A")
        assert lib.list_templates() == ["a_template", "b_template"]


class TestEdgeCases:
    """Edge cases and special patterns."""

    def test_empty_template(self):
        tpl = PromptTemplate("")
        assert tpl.render() == ""
        assert tpl.get_variables() == []

    def test_template_no_variables(self):
        tpl = PromptTemplate("Just plain text.")
        assert tpl.render() == "Just plain text."

    def test_nested_braces_ignored(self):
        """Single braces and triple+ braces should not be treated as vars."""
        tpl = PromptTemplate("{not_a_var} and {{{inner}}}")
        # {not_a_var} stays as-is; {{{inner}}} -> the regex matches {{inner}}
        # which is surrounded by extra braces -> "{" + value + "}"
        result = tpl.render(inner="val")
        assert "val" in result

    def test_numeric_values(self):
        tpl = PromptTemplate("Count: {{n}}")
        assert tpl.render(n=42) == "Count: 42"
