"""Smoke tests for o LLM nas integrações (adendo 8).

Cobrem: POST /api/integrations/llm/test (mock + kind inválido), criação de
integração ``llm`` (chave criptografada, ``apiKeyHint``, chave nunca sai na
API). Nível smoke, por pedido do usuário.
"""

from __future__ import annotations

import uuid


async def test_llm_test_mock_success(full_client, session):
    """provider_kind=mock devolve sucesso sem chamada real, sem ecoar a chave."""
    r = await full_client.post(
        "/api/integrations/llm/test",
        json={
            "type": "llm",
            "config": {
                "provider_kind": "mock",
                "base_url": "",
                "api_key": "sk-SEGREDO1234567890",
                "model": "gpt-4o-mini",
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["model"] == "gpt-4o-mini"
    # A chave nunca é ecoada.
    assert "SEGREDO" not in r.text


async def test_llm_test_invalid_kind(full_client):
    """provider_kind inválido devolve ok=False."""
    r = await full_client.post(
        "/api/integrations/llm/test",
        json={"type": "llm", "config": {"provider_kind": "anthropic"}},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


async def test_create_llm_integration_seals_key(full_client, session):
    """Criar integração llm: chave criptografada, hint devolvido, chave nunca sai."""
    r = await full_client.post(
        "/api/integrations",
        json={
            "type": "llm",
            "name": f"llm-{uuid.uuid4().hex[:8]}",
            "config": {
                "provider_kind": "openai_compatible",
                "base_url": "http://llm.local/v1",
                "api_key": "sk-SEGREDO1234567890",
                "models": ["gpt-4o-mini"],
                "default_model": "gpt-4o-mini",
            },
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "llm"
    # Chave nunca sai na API.
    assert "SEGREDO" not in r.text
    assert "api_key" not in body["config"]
    assert "api_key_encrypted" not in body["config"]
    # Hint com os últimos 4 caracteres.
    assert body["apiKeyHint"] == "…7890"


