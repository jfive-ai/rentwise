"""Round-trip tests: for every fixture, mock the LLM to return the expected tool
call, then assert the client parses it into the same NormalizedQuery.

This locks down the parser/schema contract. Whether the real model can produce
that tool call is what the live test (test_translate_query_live.py) checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from rentwise.llm import LLMClient
from rentwise.models import NormalizedQuery

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load(filename: str) -> list[dict[str, Any]]:
    with (_FIXTURES_DIR / filename).open() as f:
        return json.load(f)


def _ids(cases: list[dict[str, Any]]) -> list[str]:
    return [c["input"][:50] for c in cases]


def _tool_response(args: dict[str, Any]) -> Any:
    class _Fn:
        name = "submit_query"
        arguments = json.dumps(args)

    return type(
        "Resp",
        (),
        {
            "model": "mock-model",
            "choices": [
                type(
                    "C",
                    (),
                    {
                        "message": type(
                            "M", (), {"tool_calls": [type("T", (), {"function": _Fn})()]}
                        )()
                    },
                )()
            ],
        },
    )()


_EN_CASES = _load("translate_query_en.json")
_KO_CASES = _load("translate_query_ko.json")


@pytest.mark.parametrize("case", _EN_CASES, ids=_ids(_EN_CASES))
async def test_en_fixture_round_trip(case, monkeypatch) -> None:
    mock = AsyncMock(return_value=_tool_response(case["expected"]))
    monkeypatch.setattr("rentwise.llm.client.acompletion", mock)
    result = await LLMClient().translate_query(case["input"])
    assert result.query == NormalizedQuery.model_validate(case["expected"])
    assert result.lang_detected == "en"


@pytest.mark.parametrize("case", _KO_CASES, ids=_ids(_KO_CASES))
async def test_ko_fixture_round_trip(case, monkeypatch) -> None:
    mock = AsyncMock(return_value=_tool_response(case["expected"]))
    monkeypatch.setattr("rentwise.llm.client.acompletion", mock)
    result = await LLMClient().translate_query(case["input"])
    assert result.query == NormalizedQuery.model_validate(case["expected"])
    assert result.lang_detected == "ko"
