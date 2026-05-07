"""LLM prompts and the tool-use schema mirroring NormalizedQuery.

The schema is generated from the Pydantic model so it stays in sync if fields
are added; enums for PetPolicy / FurnishedPolicy are wired in explicitly so the
LLM is constrained to valid values.
"""

from __future__ import annotations

from typing import Any

from rentwise.models import FurnishedPolicy, NormalizedQuery, PetPolicy


def _build_query_tool_schema() -> dict[str, Any]:
    json_schema = NormalizedQuery.model_json_schema()
    properties = dict(json_schema.get("properties", {}))

    # Pydantic emits $ref for enums; flatten into inline enums for LiteLLM.
    properties["pets"] = {
        "type": "string",
        "enum": [m.value for m in PetPolicy],
        "description": "User preference for pets. Default 'any' if not stated.",
    }
    properties["furnished"] = {
        "type": "string",
        "enum": [m.value for m in FurnishedPolicy],
        "description": "User preference for furnished. Default 'any' if not stated.",
    }

    return {
        "type": "function",
        "function": {
            "name": "submit_query",
            "description": (
                "Return the user's rental search criteria as a structured query. "
                "Only include fields the user actually mentioned; leave other "
                "fields at their defaults."
            ),
            "parameters": {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            },
        },
    }


QUERY_TOOL_SCHEMA: dict[str, Any] = _build_query_tool_schema()
