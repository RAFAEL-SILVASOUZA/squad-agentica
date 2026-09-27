"""LLM client interface + factory with mock and OpenAI providers.

Dono: infra-docker. Contrato §4: provider `mock` = respostas determinísticas;
provider real só entra se LLM_PROVIDER=openai E (OPENAI_API_KEY ou OPENAI_BASE_URL
presente); OPENAI_BASE_URL aponta para servidor compatível (chave vazia aceita).
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


# Servidores locais compatíveis com OpenAI aceitam qualquer chave; o SDK exige
# uma não vazia.
LOCAL_API_KEY_PLACEHOLDER = "local"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class OpenAILLMClient:
    """Provider real: OpenAI ou servidor compatível (``OPENAI_BASE_URL``).

    ``model`` fixo (``LLM_MODEL``) tem precedência sobre o modelo pedido pela
    chamada: um servidor local só serve os modelos que carregou.
    """

    def __init__(self, api_key: str, base_url: str = "", model: str = "") -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key or LOCAL_API_KEY_PLACEHOLDER, base_url=base_url or None
        )
        self._model = model

    async def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        model = self._model or str(kwargs.get("model") or DEFAULT_OPENAI_MODEL)
        response = await self._client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content or ""


def get_llm_client() -> LLMClient:
    """Fábrica: provider real com LLM_PROVIDER=openai e chave ou URL configurada."""
    if settings.llm_provider == "openai" and (settings.openai_api_key or settings.openai_base_url):
        return OpenAILLMClient(
            settings.openai_api_key, settings.openai_base_url, settings.llm_model
        )
    return MockLLMClient()
