"""LLM client interface + factory with mock and OpenAI providers (worker).

Dono: rt-worker (FASE 6). O worker usa o mesmo contrato de LLM do
orchestrator: provider ``mock`` = respostas deterministicas; provider real
so entra se ``LLM_PROVIDER=openai`` E (``OPENAI_API_KEY`` ou ``OPENAI_BASE_URL``).

Interface: ``LLMClient.chat(messages, **kwargs) -> str``.
Suporta tool calling via ``tools`` kwarg (formato OpenAI function calling).
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol


class LLMClient(Protocol):
    """Interface minima de LLM consumida pela execucao de agentes."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str = "gpt-4o-mini",
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Recebe a lista de mensagens e devolve a resposta estruturada.

        Returns:
            dict com:
            - ``content``: str (texto da resposta, pode ser vazio se tool_call)
            - ``tool_calls``: list[dict] | None (se o LLM pediu tool calls)
              Cada tool_call: ``{"id": str, "function": {"name": str, "arguments": str}}``
        """
        ...


class MockLLMClient:
    """Provider deterministico para testes e desenvolvimento.

    - Devolve um texto derivado da ultima mensagem de usuario.
    - Se ``tools`` for fornecido e a ultima mensagem contiver ``TOOL_CALL``,
      simula um tool call para testar o loop.
    - Inclui um marker verificavel nos testes (``MOCK_LLM``).
    """

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str = "gpt-4o-mini",
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        # Se a mensagem de usuario contiver TOOL_CALL, simula um tool call.
        if "TOOL_CALL" in last_user and tools:
            tool_name = tools[0]["function"]["name"]
            tool_call = {
                "id": "call_mock_1",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps({"command": "echo hello"}),
                },
            }
            return {"content": "", "tool_calls": [tool_call]}

        # Default: devolve JSON com output + action.
        content = json.dumps(
            {
                "output": f"MOCK_LLM: echo of: {last_user[:200]}",
                "_action": "follow",
            },
            ensure_ascii=False,
        )
        return {"content": content, "tool_calls": None}


# Servidores locais compativeis com OpenAI aceitam qualquer chave; o SDK exige
# uma nao vazia.
LOCAL_API_KEY_PLACEHOLDER = "local"


class OpenAILLMClient:
    """Provider real: OpenAI ou servidor compativel (``OPENAI_BASE_URL``).

    ``model`` fixo (``LLM_MODEL``) tem precedencia sobre o modelo do snapshot:
    um servidor local so serve os modelos que carregou.
    """

    def __init__(self, api_key: str, base_url: str = "", model: str = "") -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key or LOCAL_API_KEY_PLACEHOLDER, base_url=base_url or None
        )
        self._model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str = "gpt-4o-mini",
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._model or model,
            "messages": messages,
        }
        if tools:
            params["tools"] = tools

        response = await self._client.chat.completions.create(**params)
        choice = response.choices[0].message

        tool_calls = None
        if choice.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.tool_calls
            ]

        return {
            "content": choice.content or "",
            "tool_calls": tool_calls,
        }


def get_llm_client() -> LLMClient:
    """Fabrica: provider real com LLM_PROVIDER=openai e chave ou URL configurada."""
    provider = os.environ.get("LLM_PROVIDER", "mock")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    if provider == "openai" and (api_key or base_url):
        return OpenAILLMClient(api_key, base_url, os.environ.get("LLM_MODEL", ""))
    return MockLLMClient()
