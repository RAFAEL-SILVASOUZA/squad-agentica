"""Provedor compatível com OpenAI configurável (qa-fix-rest).

Cobre: OPENAI_BASE_URL/LLM_MODEL repassados ao SDK, chave vazia aceita com
placeholder, EMBEDDING_BASE_URL/EMBEDDING_MODEL e padding até EMBEDDING_DIM.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import embeddings as emb_mod
from app.core import llm as llm_mod
from app.core.config import settings


def _completion(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class TestLLMFactory:
    def test_mock_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")
        assert isinstance(llm_mod.get_llm_client(), llm_mod.MockLLMClient)

    def test_openai_with_base_url_and_empty_key(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")
        monkeypatch.setattr(settings, "openai_base_url", "http://llm.local:1234/v1")
        monkeypatch.setattr(settings, "llm_model", "local-model")
        with patch("openai.AsyncOpenAI") as sdk:
            client = llm_mod.get_llm_client()
        assert isinstance(client, llm_mod.OpenAILLMClient)
        sdk.assert_called_once_with(
            api_key=llm_mod.LOCAL_API_KEY_PLACEHOLDER, base_url="http://llm.local:1234/v1"
        )

    def test_openai_without_key_nor_url_falls_back_to_mock(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")
        monkeypatch.setattr(settings, "openai_base_url", "")
        assert isinstance(llm_mod.get_llm_client(), llm_mod.MockLLMClient)


class TestOpenAILLMClient:
    @pytest.mark.asyncio
    async def test_configured_model_overrides_requested(self):
        with patch("openai.AsyncOpenAI") as sdk:
            create = AsyncMock(return_value=_completion("ok"))
            sdk.return_value.chat.completions.create = create
            client = llm_mod.OpenAILLMClient("", "http://x/v1", "local-model")
            text = await client.chat([{"role": "user", "content": "hi"}], model="gpt-4o")
        assert text == "ok"
        assert create.await_args.kwargs["model"] == "local-model"

    @pytest.mark.asyncio
    async def test_requested_model_used_without_configured(self):
        with patch("openai.AsyncOpenAI") as sdk:
            create = AsyncMock(return_value=_completion("ok"))
            sdk.return_value.chat.completions.create = create
            client = llm_mod.OpenAILLMClient("sk", "", "")
            await client.chat([{"role": "user", "content": "hi"}], model="gpt-4o")
        assert create.await_args.kwargs["model"] == "gpt-4o"


class TestOpenAIEmbedder:
    def _embedder(self, vectors: list[list[float]], dim: int = 8):
        sdk = MagicMock()
        sdk.return_value.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=v) for v in vectors]
        )
        with patch("openai.OpenAI", sdk):
            embedder = emb_mod.OpenAIEmbedder("", dim, "http://emb.local/v1", "nomic")
        return embedder, sdk

    def test_base_url_model_and_placeholder_key(self):
        embedder, sdk = self._embedder([[1.0, 0.0]])
        embedder.embed("hello")
        sdk.assert_called_once_with(
            api_key=llm_mod.LOCAL_API_KEY_PLACEHOLDER, base_url="http://emb.local/v1"
        )
        assert sdk.return_value.embeddings.create.call_args.kwargs["model"] == "nomic"

    def test_smaller_vector_padded_with_zeros(self):
        embedder, _ = self._embedder([[3.0, 4.0]], dim=8)
        vec = embedder.embed("hello")
        assert len(vec) == 8
        assert vec[:2] == pytest.approx([0.6, 0.8])
        assert vec[2:] == [0.0] * 6
        assert math.isclose(sum(v * v for v in vec), 1.0)

    def test_larger_vector_rejected(self):
        embedder, _ = self._embedder([[0.1] * 9], dim=8)
        with pytest.raises(ValueError, match="EMBEDDING_DIM=8"):
            embedder.embed("hello")

    def test_factory_uses_embedding_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "embedding_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")
        monkeypatch.setattr(settings, "openai_base_url", "http://llm/v1")
        monkeypatch.setattr(settings, "embedding_base_url", "http://emb/v1")
        monkeypatch.setattr(settings, "embedding_model", "nomic")
        with patch("openai.OpenAI") as sdk:
            embedder = emb_mod.get_embedder()
        assert isinstance(embedder, emb_mod.OpenAIEmbedder)
        sdk.assert_called_once_with(api_key=llm_mod.LOCAL_API_KEY_PLACEHOLDER, base_url="http://emb/v1")
