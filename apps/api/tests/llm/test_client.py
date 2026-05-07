"""LLMClient.translate_query unit tests with mocked LiteLLM."""

from __future__ import annotations

import json
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest

from rentwise.llm import LLMClient, LLMMalformedResponse, LLMTransportError
from rentwise.models import NormalizedQuery, PetPolicy
from rentwise.settings import settings


def _tool_call_response(
    arguments: dict[str, Any], model: str = "openrouter/qwen/qwen-2.5-72b-instruct:free"
) -> Any:
    """Shape of the LiteLLM response object we care about."""

    class _ToolFn:
        def __init__(self, args: dict[str, Any]) -> None:
            self.name = "submit_query"
            self.arguments = json.dumps(args)

    class _ToolCall:
        def __init__(self, args: dict[str, Any]) -> None:
            self.function = _ToolFn(args)

    class _Message:
        def __init__(self, calls: list[_ToolCall]) -> None:
            self.tool_calls = calls

    class _Choice:
        def __init__(self, calls: list[_ToolCall]) -> None:
            self.message = _Message(calls)

    class _Resp:
        def __init__(self, calls: list[_ToolCall]) -> None:
            self.model = model
            self.choices = [_Choice(calls)]

    return _Resp([_ToolCall(arguments)])


@pytest.fixture
def patch_acompletion(monkeypatch: pytest.MonkeyPatch):
    """Patches the `acompletion` symbol imported into client.py."""

    def _set(side_effect_or_return: Any) -> AsyncMock:
        mock = AsyncMock()
        if isinstance(side_effect_or_return, list):
            mock.side_effect = side_effect_or_return
        elif isinstance(side_effect_or_return, BaseException):
            mock.side_effect = side_effect_or_return
        else:
            mock.return_value = side_effect_or_return
        monkeypatch.setattr("rentwise.llm.client.acompletion", mock)
        return mock

    return _set


async def test_translate_query_en_happy_path(patch_acompletion) -> None:
    expected = {"bedrooms_min": 2, "price_max": 3000, "neighborhoods": ["Kitsilano"], "pets": "ok"}
    mock = patch_acompletion(_tool_call_response(expected))

    client = LLMClient()
    result = await client.translate_query("2br Kits under 3000 pet ok")

    assert result.query == NormalizedQuery(
        bedrooms_min=2, price_max=3000, neighborhoods=["Kitsilano"], pets=PetPolicy.OK
    )
    assert result.lang_detected == "en"
    assert result.model_used == settings.rentwise_llm_model
    assert mock.await_count == 1
    _, kwargs = mock.call_args
    assert kwargs["model"] == settings.rentwise_llm_model
    assert kwargs["tool_choice"]["function"]["name"] == "submit_query"


async def test_translate_query_ko_uses_korean_prompt(patch_acompletion) -> None:
    expected = {"bedrooms_min": 2, "price_max": 3000, "neighborhoods": ["Kitsilano"]}
    mock = patch_acompletion(_tool_call_response(expected))

    client = LLMClient()
    result = await client.translate_query("키츠 2베드 3000불 이하")

    assert result.lang_detected == "ko"
    msgs = mock.call_args.kwargs["messages"]
    # KO prompt has Korean rules header.
    assert "한국어" in msgs[0]["content"] or "도구" in msgs[0]["content"]


async def test_translate_query_falls_back_on_primary_failure(
    patch_acompletion, monkeypatch
) -> None:
    # Pin both models so the test is hermetic regardless of env / .env overrides.
    monkeypatch.setattr(
        "rentwise.llm.client.settings.rentwise_llm_model",
        "openrouter/qwen/qwen-2.5-72b-instruct:free",
    )
    monkeypatch.setattr(
        "rentwise.llm.client.settings.rentwise_llm_fallback_model",
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    )
    expected = {"bedrooms_min": 1}
    mock = patch_acompletion(
        [
            RuntimeError("primary down"),
            _tool_call_response(
                expected, model="openrouter/meta-llama/llama-3.3-70b-instruct:free"
            ),
        ]
    )

    client = LLMClient()
    result = await client.translate_query("1br anywhere")

    assert mock.await_count == 2
    # First call was the primary; second call was the fallback.
    first_kwargs = mock.call_args_list[0].kwargs
    second_kwargs = mock.call_args_list[1].kwargs
    assert first_kwargs["model"] == "openrouter/qwen/qwen-2.5-72b-instruct:free"
    assert second_kwargs["model"] == "openrouter/meta-llama/llama-3.3-70b-instruct:free"
    assert result.model_used == "openrouter/meta-llama/llama-3.3-70b-instruct:free"
    assert result.query.bedrooms_min == 1


async def test_translate_query_raises_transport_error_when_no_fallback(
    patch_acompletion, monkeypatch
) -> None:
    monkeypatch.setattr("rentwise.llm.client.settings.rentwise_llm_fallback_model", None)
    patch_acompletion(RuntimeError("kaboom"))

    client = LLMClient()
    with pytest.raises(LLMTransportError):
        await client.translate_query("anything")


async def test_translate_query_raises_malformed_when_no_tool_call(patch_acompletion) -> None:
    class _NoCalls:
        model: ClassVar[str] = "x"
        choices: ClassVar[list[Any]] = [
            type("C", (), {"message": type("M", (), {"tool_calls": []})()})()
        ]

    patch_acompletion(_NoCalls())
    client = LLMClient()
    with pytest.raises(LLMMalformedResponse):
        await client.translate_query("anything")


async def test_translate_query_raises_malformed_on_bad_json(patch_acompletion) -> None:
    class _BadCall:
        function = type("F", (), {"name": "submit_query", "arguments": "{not-json"})()

    class _Resp:
        model: ClassVar[str] = "x"
        choices: ClassVar[list[Any]] = [
            type("C", (), {"message": type("M", (), {"tool_calls": [_BadCall()]})()})()
        ]

    patch_acompletion(_Resp())
    client = LLMClient()
    with pytest.raises(LLMMalformedResponse):
        await client.translate_query("anything")


async def test_translate_query_raises_malformed_on_unknown_field(patch_acompletion) -> None:
    # NormalizedQuery has no `garage` field; this would silently get dropped on .model_validate
    # if we used model_validate without strict=True. Strict validation is part of the contract.
    patch_acompletion(_tool_call_response({"garage": True}))
    client = LLMClient()
    with pytest.raises(LLMMalformedResponse):
        await client.translate_query("anything")


async def test_translate_query_raises_malformed_on_wrong_tool_name(patch_acompletion) -> None:
    class _BadName:
        function = type("F", (), {"name": "not_submit_query", "arguments": '{"bedrooms_min": 1}'})()

    class _Resp:
        model: ClassVar[str] = "x"
        choices: ClassVar[list[Any]] = [
            type("C", (), {"message": type("M", (), {"tool_calls": [_BadName()]})()})()
        ]

    patch_acompletion(_Resp())
    client = LLMClient()
    with pytest.raises(LLMMalformedResponse, match="not_submit_query"):
        await client.translate_query("anything")


async def test_translate_query_raises_malformed_on_validation_error(patch_acompletion) -> None:
    # bedrooms_min must be a number; passing a string triggers Pydantic ValidationError
    # AFTER the unknown-field check passes (the field name is valid).
    bad_args = {"bedrooms_min": "not a number"}

    class _Fn:
        name = "submit_query"
        arguments = __import__("json").dumps(bad_args)

    class _Resp:
        model: ClassVar[str] = "x"
        choices: ClassVar[list[Any]] = [
            type(
                "C",
                (),
                {"message": type("M", (), {"tool_calls": [type("T", (), {"function": _Fn})()]})()},
            )()
        ]

    patch_acompletion(_Resp())
    client = LLMClient()
    with pytest.raises(LLMMalformedResponse):
        await client.translate_query("anything")


@pytest.mark.parametrize(
    ("model", "key_attr", "key_value", "expected"),
    [
        ("openrouter/qwen/qwen-2.5-72b-instruct:free", "openrouter_api_key", "sk-or-v1-x", True),
        ("openrouter/qwen/qwen-2.5-72b-instruct:free", "openrouter_api_key", None, False),
        ("anthropic/claude-sonnet-4", "anthropic_api_key", "sk-ant-x", True),
        ("anthropic/claude-sonnet-4", "anthropic_api_key", None, False),
        ("openai/gpt-4o-mini", "openai_api_key", "sk-x", True),
        ("openai/gpt-4o-mini", "openai_api_key", None, False),
        ("google/gemini-2.5-flash", "google_api_key", "g-x", True),
        ("gemini/gemini-1.5", "google_api_key", "g-x", True),
        ("ollama/llama3", "openrouter_api_key", None, True),  # ollama needs no key
        ("unknown-provider/model", "openrouter_api_key", "doesnt-matter", False),
    ],
)
def test_is_configured_per_provider(
    monkeypatch, model: str, key_attr: str, key_value, expected: bool
) -> None:
    """is_configured() reads model + provider key live; covers all match arms."""
    monkeypatch.setattr("rentwise.llm.client.settings.rentwise_llm_model", model)
    monkeypatch.setattr(f"rentwise.llm.client.settings.{key_attr}", key_value)
    assert LLMClient().is_configured() is expected


async def test_translate_query_raises_malformed_when_response_shape_unexpected(
    patch_acompletion,
) -> None:
    """Cover the bare `except Exception` in _parse_tool_call.

    A response missing `.choices` entirely (or `.choices[0].message`) shouldn't
    crash the server with AttributeError — it should map to LLMMalformedResponse.
    """

    class _BrokenResp:
        model = "x"
        # No `choices` attribute at all.

    patch_acompletion(_BrokenResp())
    client = LLMClient()
    with pytest.raises(LLMMalformedResponse):
        await client.translate_query("anything")


async def test_translate_query_threads_openrouter_api_key(patch_acompletion, monkeypatch) -> None:
    monkeypatch.setattr(
        "rentwise.llm.client.settings.rentwise_llm_model",
        "openrouter/qwen/qwen-2.5-72b-instruct:free",
    )
    monkeypatch.setattr("rentwise.llm.client.settings.rentwise_llm_fallback_model", None)
    monkeypatch.setattr("rentwise.llm.client.settings.openrouter_api_key", "sk-or-test")
    mock = patch_acompletion(_tool_call_response({"bedrooms_min": 1}))
    await LLMClient().translate_query("anything")
    assert mock.call_args.kwargs["api_key"] == "sk-or-test"


async def test_translate_query_threads_ollama_base_url(patch_acompletion, monkeypatch) -> None:
    monkeypatch.setattr("rentwise.llm.client.settings.rentwise_llm_model", "ollama/llama3")
    monkeypatch.setattr("rentwise.llm.client.settings.rentwise_llm_fallback_model", None)
    monkeypatch.setattr("rentwise.llm.client.settings.ollama_base_url", "http://localhost:11434")
    mock = patch_acompletion(_tool_call_response({"bedrooms_min": 1}))
    await LLMClient().translate_query("anything")
    assert mock.call_args.kwargs["api_base"] == "http://localhost:11434"


async def test_translate_query_omits_api_key_when_unset(patch_acompletion, monkeypatch) -> None:
    monkeypatch.setattr("rentwise.llm.client.settings.rentwise_llm_model", "anthropic/claude")
    monkeypatch.setattr("rentwise.llm.client.settings.rentwise_llm_fallback_model", None)
    monkeypatch.setattr("rentwise.llm.client.settings.anthropic_api_key", None)
    mock = patch_acompletion(_tool_call_response({"bedrooms_min": 1}))
    await LLMClient().translate_query("anything")
    assert "api_key" not in mock.call_args.kwargs


async def test_translate_query_system_message_includes_today(patch_acompletion) -> None:
    mock = patch_acompletion(_tool_call_response({"bedrooms_min": 1}))
    await LLMClient().translate_query("1br anywhere")
    msgs = mock.call_args.kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"].startswith("Today's date is ")
