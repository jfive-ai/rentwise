"""Tool-use schema and prompt-module tests."""

from __future__ import annotations

import pytest

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
    from rentwise.models import PetPolicy

    pets_prop = QUERY_TOOL_SCHEMA["function"]["parameters"]["properties"]["pets"]
    # Use the model's enum as the source of truth so renames stay in sync.
    assert set(pets_prop["enum"]) == {m.value for m in PetPolicy}


def test_query_tool_schema_furnished_enum_matches_policy() -> None:
    from rentwise.models import FurnishedPolicy

    fp = QUERY_TOOL_SCHEMA["function"]["parameters"]["properties"]["furnished"]
    assert set(fp["enum"]) == {m.value for m in FurnishedPolicy}


def test_build_query_tool_schema_raises_on_unhandled_ref(monkeypatch) -> None:
    from rentwise.llm import prompts as prompts_mod

    def fake_schema(*args, **kwargs):
        return {"properties": {"new_enum_field": {"$ref": "#/$defs/Foo"}}}

    monkeypatch.setattr(NormalizedQuery, "model_json_schema", fake_schema)
    with pytest.raises(RuntimeError, match="new_enum_field"):
        prompts_mod._build_query_tool_schema()
