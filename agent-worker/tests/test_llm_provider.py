"""Provedor compativel com OpenAI configuravel no worker (qa-fix-rest)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core import llm as llm_mod


def test_mock_by_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(llm_mod.get_llm_client(), llm_mod.MockLLMClient)


def test_base_url_and_empty_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://llm.local:1234/v1")
    monkeypatch.setenv("LLM_MODEL", "local-model")
    with patch("openai.AsyncOpenAI") as sdk:
        client = llm_mod.get_llm_client()
    assert isinstance(client, llm_mod.OpenAILLMClient)
    sdk.assert_called_once_with(
        api_key=llm_mod.LOCAL_API_KEY_PLACEHOLDER, base_url="http://llm.local:1234/v1"
    )


def test_no_key_nor_url_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert isinstance(llm_mod.get_llm_client(), llm_mod.MockLLMClient)


@pytest.mark.asyncio
async def test_configured_model_overrides_snapshot_model():
    message = SimpleNamespace(content="ok", tool_calls=None)
    with patch("openai.AsyncOpenAI") as sdk:
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=message)]))
        sdk.return_value.chat.completions.create = create
        client = llm_mod.OpenAILLMClient("", "http://x/v1", "local-model")
        result = await client.chat([{"role": "user", "content": "hi"}], model="gpt-4o")
    assert result == {"content": "ok", "tool_calls": None}
    assert create.await_args.kwargs["model"] == "local-model"


@pytest.mark.asyncio
async def test_tool_calls_carry_type_function():
    """Sem "type", o llama.cpp rejeita o histórico com 500 "Missing tool call type"."""
    fn = SimpleNamespace(name="list_directory", arguments='{"path": "."}')
    message = SimpleNamespace(content="", tool_calls=[SimpleNamespace(id="c1", function=fn)])
    with patch("openai.AsyncOpenAI") as sdk:
        sdk.return_value.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=message)])
        )
        client = llm_mod.OpenAILLMClient("", "http://x/v1", "m")
        result = await client.chat(
            [{"role": "user", "content": "hi"}], tools=[{"type": "function"}]
        )
    expected_fn = {"name": "list_directory", "arguments": '{"path": "."}'}
    assert result["tool_calls"] == [{"id": "c1", "type": "function", "function": expected_fn}]
