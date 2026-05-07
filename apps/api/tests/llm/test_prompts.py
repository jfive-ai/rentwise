"""Tool-use schema and prompt-module tests."""

from __future__ import annotations

import pytest

from rentwise.llm.prompts import (
    QUERY_TOOL_SCHEMA,
    SYSTEM_PROMPT_EN,
    SYSTEM_PROMPT_KO,
    detect_language,
    pick_prompt,
)
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


def test_system_prompts_mention_vancouver_and_tool() -> None:
    for prompt in (SYSTEM_PROMPT_EN, SYSTEM_PROMPT_KO):
        assert "Vancouver" in prompt or "밴쿠버" in prompt
        assert "submit_query" in prompt


def test_system_prompt_en_lists_known_neighborhoods() -> None:
    for hood in ["Kitsilano", "Mount Pleasant", "Yaletown", "East Vancouver"]:
        assert hood in SYSTEM_PROMPT_EN


def test_system_prompt_ko_includes_korean_transliterations() -> None:
    # Common Korean spellings users actually type.
    for token in ["키츠", "이스트밴", "밴쿠버", "옐레타운", "마운트플레전트", "키칠라노"]:
        assert token in SYSTEM_PROMPT_KO


def test_system_prompt_ko_includes_unsupported_phrases_rule() -> None:
    """KO prompt must mirror EN's permission to include unsupported phrases in
    free_text_keywords; otherwise KO speakers get a strictly weaker prompt.
    """
    assert "진짜 지원되지 않는 표현" in SYSTEM_PROMPT_KO


def test_neighborhoods_match_filter_panel() -> None:
    """The prompt's neighborhood list must equal the frontend's NEIGHBORHOODS const,
    or NL parses will produce queries the filter UI can't reproduce.
    """
    import re
    from pathlib import Path

    from rentwise.llm import prompts as prompts_mod

    panel = (
        Path(__file__).resolve().parents[4]
        / "apps"
        / "web"
        / "src"
        / "components"
        / "FilterPanel.tsx"
    )
    text = panel.read_text(encoding="utf-8")
    match = re.search(r"export const NEIGHBORHOODS = \[(.*?)\];", text, re.DOTALL)
    assert match, "Could not locate NEIGHBORHOODS in FilterPanel.tsx"
    panel_neighborhoods = sorted(re.findall(r'"([^"]+)"', match.group(1)))
    assert sorted(prompts_mod._NEIGHBORHOODS) == panel_neighborhoods, (
        "API and Web neighborhood lists drifted; update both."
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2br Kitsilano under 3000", "en"),
        ("키츠 2베드 3000불 이하", "ko"),
        ("Studio downtown 한 달 1500", "ko"),  # mixed → KO when any Hangul present
        ("", "en"),  # empty defaults to English
        ("    ", "en"),
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_pick_prompt_returns_correct_language() -> None:
    assert pick_prompt("en") is SYSTEM_PROMPT_EN
    assert pick_prompt("ko") is SYSTEM_PROMPT_KO
    # Unknown lang code falls back to English.
    assert pick_prompt("zz") is SYSTEM_PROMPT_EN
