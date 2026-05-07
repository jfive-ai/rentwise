"""Optional end-to-end translate-query test against a real OpenRouter free model.

Skipped unless `RUN_LIVE_LLM_TESTS=1` is in env AND `OPENROUTER_API_KEY` is set.
This guards against accidental quota burn in CI.

To run locally:
    RUN_LIVE_LLM_TESTS=1 OPENROUTER_API_KEY=sk-or-... pytest tests/llm/test_translate_query_live.py -m live -v
"""

from __future__ import annotations

import os

import pytest

from rentwise.llm import LLMClient

pytestmark = pytest.mark.live

_RUN = os.environ.get("RUN_LIVE_LLM_TESTS") == "1" and bool(os.environ.get("OPENROUTER_API_KEY"))

if not _RUN:
    pytest.skip(
        "Live LLM tests skipped. Set RUN_LIVE_LLM_TESTS=1 and OPENROUTER_API_KEY to run.",
        allow_module_level=True,
    )


async def test_live_en_translate_kitsilano() -> None:
    client = LLMClient()
    result = await client.translate_query("2 bedroom in Kitsilano under 3000")
    assert result.lang_detected == "en"
    # Loose assertion — the model is allowed flexibility on neighborhood casing
    # but it must extract bedrooms and price.
    assert result.query.bedrooms_min == 2
    assert result.query.price_max == 3000
    assert any(n.lower() == "kitsilano" for n in result.query.neighborhoods)


async def test_live_ko_translate_kits() -> None:
    client = LLMClient()
    result = await client.translate_query("키츠에 2베드 3000불 이하")
    assert result.lang_detected == "ko"
    assert result.query.bedrooms_min == 2
    assert result.query.price_max == 3000
    assert any(n.lower() == "kitsilano" for n in result.query.neighborhoods)
