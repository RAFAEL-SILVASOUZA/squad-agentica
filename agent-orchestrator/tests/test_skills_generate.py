"""Tests for POST /api/skills/generate (geração de skill por IA, interativa).

Cobre:
- LLM devolve pergunta (status='questions') → response com question
- LLM devolve skill completa (status='done') → response com skill validada
- LLM devolve JSON em cerca de markdown → parseado
- LLM devolve JSON inválido → 502 llm_invalid_response
- LLM não configurada → 400 llm_not_configured
- Histórico de respostas é enviado ao LLM
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db

# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------


class MockGenerateLLM:
    """LLM mock que devolve uma resposta fixa (pergunta ou skill)."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.last_messages: list[dict[str, str]] | None = None
        self.call_count = 0

    async def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.call_count += 1
        self.last_messages = messages
        return self._response


DONE_SKILL_JSON = json.dumps(
    {
        "status": "done",
        "skill": {
            "name": "code-reviewer",
            "description": "Revisa código",
            "category": "code",
            "template": "Revise {code} com foco em {focus}.",
            "variables": ["code", "focus"],
            "inputs": [{"name": "code", "type": "code", "required": True}],
            "outputs": [{"name": "review", "type": "document", "required": False}],
            "required_integrations": [],
        },
    }
)

QUESTION_JSON = json.dumps(
    {
        "status": "questions",
        "question": {
            "text": "Qual o foco da revisão?",
            "options": ["segurança", "performance", "legibilidade"],
        },
    }
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="gen-skill@example.com",
        name="Gen Skill User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_app(session: AsyncSession, test_user: User):
    from app.api.skills import router as skills_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(skills_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return app


@pytest_asyncio.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateSkill:
    async def test_returns_question(self, client: AsyncClient) -> None:
        """LLM devolve pergunta → response status='questions' com question."""
        llm = MockGenerateLLM(QUESTION_JSON)
        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(return_value=llm)):
            resp = await client.post(
                "/api/skills/generate",
                json={"description": "Quero uma skill de code review"},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "questions"
        assert data["question"]["text"] == "Qual o foco da revisão?"
        assert data["question"]["options"] == ["segurança", "performance", "legibilidade"]
        assert data["skill"] is None

    async def test_returns_done_skill(self, client: AsyncClient) -> None:
        """LLM devolve skill completa → response status='done' com skill validada."""
        llm = MockGenerateLLM(DONE_SKILL_JSON)
        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(return_value=llm)):
            resp = await client.post(
                "/api/skills/generate",
                json={"description": "Quero uma skill de code review"},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "done"
        skill = data["skill"]
        assert skill["name"] == "code-reviewer"
        assert skill["category"] == "code"
        assert skill["variables"] == ["code", "focus"]
        assert skill["inputs"][0]["name"] == "code"
        assert data["question"] is None

    async def test_parses_json_in_markdown_fence(self, client: AsyncClient) -> None:
        """LLM devolve JSON dentro de cerca de markdown → parseado."""
        llm = MockGenerateLLM(f"Claro!\n```json\n{DONE_SKILL_JSON}\n```")
        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(return_value=llm)):
            resp = await client.post(
                "/api/skills/generate",
                json={"description": "skill de code review"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "done"

    async def test_invalid_json_returns_502(self, client: AsyncClient) -> None:
        """LLM devolve texto sem JSON → 502 llm_invalid_response."""
        llm = MockGenerateLLM("Não sei o que fazer, desculpe.")
        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(return_value=llm)):
            resp = await client.post(
                "/api/skills/generate",
                json={"description": "skill de code review"},
            )
        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] == "llm_invalid_response"

    async def test_invalid_status_returns_502(self, client: AsyncClient) -> None:
        """LLM devolve status desconhecido → 502 llm_invalid_response."""
        llm = MockGenerateLLM('{"status": "weird", "foo": 1}')
        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(return_value=llm)):
            resp = await client.post(
                "/api/skills/generate",
                json={"description": "skill de code review"},
            )
        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] == "llm_invalid_response"

    async def test_llm_not_configured_returns_400(self, client: AsyncClient) -> None:
        """Sem integração LLM → 400 llm_not_configured."""
        from app.core.errors import AppError

        async def raise_not_configured(owner_id, agent_llm=None):
            raise AppError(400, "Nenhuma integração LLM configurada.", "llm_not_configured")

        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(side_effect=raise_not_configured)):
            resp = await client.post(
                "/api/skills/generate",
                json={"description": "skill de code review"},
            )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "llm_not_configured"

    async def test_answers_history_sent_to_llm(self, client: AsyncClient) -> None:
        """O histórico de respostas é incluído na mensagem de usuário."""
        llm = MockGenerateLLM(DONE_SKILL_JSON)
        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(return_value=llm)):
            resp = await client.post(
                "/api/skills/generate",
                json={
                    "description": "Quero uma skill de code review",
                    "answers": [
                        {"question": "Qual o foco da revisão?", "answer": "segurança"}
                    ],
                },
            )
        assert resp.status_code == 200, resp.text
        assert llm.last_messages is not None
        user_msg = llm.last_messages[-1]["content"]
        assert "Quero uma skill de code review" in user_msg
        assert "Qual o foco da revisão?" in user_msg
        assert "segurança" in user_msg

    async def test_empty_description_asks_question(self, client: AsyncClient) -> None:
        """Descrição vazia → a IA é chamada e deve perguntar o que a skill faz."""
        llm = MockGenerateLLM(QUESTION_JSON)
        with patch("app.api.skills.resolve_llm_client", new=AsyncMock(return_value=llm)):
            resp = await client.post(
                "/api/skills/generate",
                json={"description": ""},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "questions"
        # A mensagem de usuário deve indicar que não há descrição.
        assert llm.last_messages is not None
        user_msg = llm.last_messages[-1]["content"]
        assert "não forneceu uma descrição" in user_msg
