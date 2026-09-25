"""LLM client interface + factory with mock and OpenAI providers.

Dono: infra-docker. Contrato §4: provider `mock` = respostas determinísticas;
provider real só entra se LLM_PROVIDER=openai E OPENAI_API_KEY presente.
"""

from __future__ import annotations

from typing import Protocol

from app.core.config import settings


class LLMClient(Protocol):
    """Interface mínima de LLM consumida pelo chat de construção e pela execução de agentes."""

    async def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        """Recebe a lista de mensagens OpenAI-style e devolve o texto da resposta."""
        ...


class MockLLMClient:
    """Provider determinístico.

    - Devolve um texto derivado da última mensagem de usuário (sustenta o chat de construção).
    - Inclui um marker verificável nos testes (``MOCK_LLM``).
    """

    async def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return f"MOCK_LLM: echo of: {last_user}"


class OpenAILLMClient:
    """Provider real (OpenAI). Só instanciado com chave presente."""

    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)

    async def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        model = kwargs.get("model", "gpt-4o-mini") if isinstance(kwargs, dict) else "gpt-4o-mini"
        response = await self._client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content or ""


def get_llm_client() -> LLMClient:
    """Fábrica: escolhe o provider conforme LLM_PROVIDER e OPENAI_API_KEY."""
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAILLMClient(settings.openai_api_key)
    return MockLLMClient()
