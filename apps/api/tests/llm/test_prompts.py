"""Tool-use schema and prompt-module tests."""

from __future__ import annotations

from rentwise.llm.prompts import QUERY_TOOL_SCHEMA
from rentwise.models import NormalizedQuery


def test_query_tool_schema_shape() -> None:
    assert QUERY_TOOL_SCHEMA["type"] == "function"
    fn = QUERY_TOOL_SCHEMA["function"]
    assert fn["name"] == "submit_query"
    assert fn["description"], "function description must be non-empty"

    params = fn["parameters"]
    assert params["type"] == "object"
    # additionalProperties=False forces the LLM to stay within the model's fields.
    assert params["additionalProperties"] is False

    # Every NormalizedQuery field must appear in the tool schema.
    model_fields = set(NormalizedQuery.model_fields.keys())
    schema_fields = set(params["properties"].keys())
    assert model_fields == schema_fields, (
        f"missing in schema: {model_fields - schema_fields}; "
        f"extra in schema: {schema_fields - model_fields}"
    )


def test_query_tool_schema_pets_enum_matches_pet_policy() -> None:
    pets_prop = QUERY_TOOL_SCHEMA["function"]["parameters"]["properties"]["pets"]
    assert set(pets_prop["enum"]) == {"required", "ok", "no", "any"}


def test_query_tool_schema_furnished_enum_matches_policy() -> None:
    fp = QUERY_TOOL_SCHEMA["function"]["parameters"]["properties"]["furnished"]
    assert set(fp["enum"]) == {"yes", "no", "any"}
