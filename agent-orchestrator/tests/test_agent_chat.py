"""Tests for agent construction chat API (D4 4.5, spec 10).

Cobre:
- Streaming SSE com LLM mock
- Confirmação salvando pelo service
- Contrato inválido rejeitado
- Isolamento por owner no chat de edição
- 429 rate limit
- Rota /api/agents/chat não capturada por {id}
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat.conversation import draft_store
from app.agents.service import AgentService
from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import Agent, User
from app.db.session import get_db

# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------


class MockChatLLM:
    """LLM mock que retorna JSON estruturado para o chat de construção."""

    def __init__(self, response: str | None = None) -> None:
        self._response = response or (
            '{"text": "Entendi! Vou configurar o agente.", '
            '"config": {"name": "Code Reviewer", "type": "reviewer", '
            '"description": "Agente de code review", '
            '"inputs": [{"name": "code", "type": "code", "required": true}], '
            '"outputs": [{"name": "review", "type": "document", "required": false}], '
            '"actions": ["follow", "finalize"]}}'
        )
        self.call_count = 0

    async def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.call_count += 1
        return self._response


class MockInvalidContractLLM:
    """LLM mock que retorna contrato inválido."""

    async def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return (
            '{"text": "Configurando...", '
            '"config": {"name": "Bad Agent", '
            '"inputs": [{"name": "x", "type": "invalid_type", "required": true}], '
            '"actions": ["bad_action"]}}'
        )


class MockAgentStorage:
    """Mock do AgentStorage para testes (in-memory)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        self.store[agent_id] = agent_yaml

    async def get_agent(self, agent_id: str) -> str:
        if agent_id not in self.store:
            raise FileNotFoundError(f"Agent {agent_id} not found")
        return self.store[agent_id]

    async def delete_agent(self, agent_id: str) -> None:
        self.store.pop(agent_id, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_storage():
    return MockAgentStorage()


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="chat-test@example.com",
        name="Chat Test User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def second_user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="chat-second@example.com",
        name="Second User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def existing_agent(session: AsyncSession, test_user: User) -> Agent:
    """Cria um agente existente para testes de edição."""
    agent = Agent(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        name="Existing Agent",
        type="developer",
        description="An existing agent",
        prompt="You are a developer.",
        strategy="",
        skills=[],
        tools=[],
        mcp_servers=[],
        knowledge=[],
        integrations=[],
        inputs=[{"name": "task", "type": "document", "required": True}],
        outputs=[{"name": "result", "type": "code", "required": False}],
        actions=["follow", "finalize"],
        model="gpt-4o",
        max_iterations=10,
        timeout=300,
        shell_access=False,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def test_app(
    session: AsyncSession,
    test_user: User,
    mock_storage: MockAgentStorage,
):
    """Cria uma app FastAPI de teste com os routers de agentes e chat."""
    from app.api.agent_chat import router as chat_router
    from app.api.agents import router as agents_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(agents_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Patch the LLM client (adendo 9: resolve pela integração; mock aqui).
    mock_llm = MockChatLLM()
    with patch("app.api.agent_chat.resolve_llm_client", new=AsyncMock(return_value=mock_llm)), \
         patch("app.api.agents._get_service") as mock_service_fn, \
         patch("app.api.agent_chat.AgentService") as mock_service_cls:
        service = AgentService(storage=mock_storage)
        mock_service_fn.return_value = service
        mock_service_cls.return_value = service
        yield app


@pytest_asyncio.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests: Route collision
# ---------------------------------------------------------------------------


class TestRouteCollision:
    """Garante que /api/agents/chat não é capturado por /api/agents/{id}."""

    async def test_chat_route_not_captured_by_id(self, client: AsyncClient):
        """POST /api/agents/chat deve funcionar (não dar 422 de UUID parse)."""
        response = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente de code review"},
        )
        # Should be 200 (SSE stream), NOT 422 (UUID validation error).
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    async def test_chat_route_with_draft_id(self, client: AsyncClient):
        """POST /api/agents/chat com draftId deve funcionar."""
        # First call to get a draftId.
        resp1 = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente"},
        )
        assert resp1.status_code == 200
        # Parse the done event to get draftId.
        events = _parse_sse_events(resp1.text)
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        draft_id = done_events[0]["data"]["draftId"]

        # Second call with draftId.
        resp2 = await client.post(
            "/api/agents/chat",
            json={"message": "Adicione integração com GitHub", "draftId": draft_id},
        )
        assert resp2.status_code == 200
        events2 = _parse_sse_events(resp2.text)
        done_events2 = [e for e in events2 if e["type"] == "done"]
        assert done_events2[0]["data"]["draftId"] == draft_id


# ---------------------------------------------------------------------------
# Tests: SSE Streaming
# ---------------------------------------------------------------------------


class TestSSEStreaming:
    """Testa o streaming SSE com LLM mock."""

    async def test_streaming_returns_text_event(self, client: AsyncClient):
        response = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente de code review de Python"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse_events(response.text)
        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) == 1
        assert "Entendi" in text_events[0]["data"]

    async def test_streaming_returns_config_update(self, client: AsyncClient):
        response = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente de code review"},
        )
        events = _parse_sse_events(response.text)
        config_events = [e for e in events if e["type"] == "config_update"]
        assert len(config_events) == 1
        config = config_events[0]["data"]
        assert config["name"] == "Code Reviewer"
        assert config["type"] == "reviewer"
        assert "inputs" in config
        assert "outputs" in config
        assert "actions" in config

    async def test_streaming_returns_done_with_draft_id(self, client: AsyncClient):
        response = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente"},
        )
        events = _parse_sse_events(response.text)
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert "draftId" in done_events[0]["data"]
        # draftId should be a valid UUID.
        uuid.UUID(done_events[0]["data"]["draftId"])

    async def test_streaming_multiple_messages_same_draft(self, client: AsyncClient):
        """Múltiplas mensagens no mesmo draft mantêm o contexto."""
        resp1 = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente de code review"},
        )
        events1 = _parse_sse_events(resp1.text)
        draft_id = [e for e in events1 if e["type"] == "done"][0]["data"]["draftId"]

        resp2 = await client.post(
            "/api/agents/chat",
            json={"message": "Adicione foco em segurança", "draftId": draft_id},
        )
        assert resp2.status_code == 200
        events2 = _parse_sse_events(resp2.text)
        # Same draftId.
        done2 = [e for e in events2 if e["type"] == "done"][0]["data"]["draftId"]
        assert done2 == draft_id


# ---------------------------------------------------------------------------
# Tests: Confirmation (save via service)
# ---------------------------------------------------------------------------


class TestConfirmation:
    """Testa a confirmação do draft salvando pelo AgentService."""

    async def test_confirm_saves_agent(self, client: AsyncClient, mock_storage: MockAgentStorage):
        # Build a draft via chat.
        resp = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente de code review"},
        )
        events = _parse_sse_events(resp.text)
        draft_id = [e for e in events if e["type"] == "done"][0]["data"]["draftId"]

        # Confirm the draft.
        confirm_resp = await client.post(
            "/api/agents/chat/confirm",
            json={"draftId": draft_id},
        )
        assert confirm_resp.status_code == 200
        data = confirm_resp.json()
        assert data["name"] == "Code Reviewer"
        assert data["type"] == "reviewer"
        assert data["id"] is not None
        # Agent should be in storage.
        assert data["id"] in mock_storage.store

    async def test_confirm_draft_without_name_rejected(self, client: AsyncClient):
        """E2: draft SEM nome não pode ser confirmado ("Unnamed Agent").

        Com o LLM mock real, um draft sem nome no config gerava um agente
        "Unnamed Agent" no banco. O confirm agora rejeita com 400
        incomplete_draft antes de gravar qualquer coisa.
        """
        unnamed_llm = MockChatLLM(
            '{"text": "Ok.", "config": {"type": "custom", '
            '"actions": ["follow", "finalize"]}}'
        )
        with patch("app.api.agent_chat.resolve_llm_client", new=AsyncMock(return_value=unnamed_llm)):
            resp = await client.post(
                "/api/agents/chat",
                json={"message": "Quero um agente"},
            )
        events = _parse_sse_events(resp.text)
        draft_id = [e for e in events if e["type"] == "done"][0]["data"]["draftId"]

        confirm_resp = await client.post(
            "/api/agents/chat/confirm",
            json={"draftId": draft_id},
        )
        assert confirm_resp.status_code == 400
        body = confirm_resp.json()
        assert body["code"] == "incomplete_draft"
        assert "name" in body["details"]["missing"]

    async def test_confirm_invalid_draft(self, client: AsyncClient):
        confirm_resp = await client.post(
            "/api/agents/chat/confirm",
            json={"draftId": str(uuid.uuid4())},
        )
        assert confirm_resp.status_code == 404
        assert confirm_resp.json()["code"] == "draft_not_found"

    async def test_confirm_missing_draft_id(self, client: AsyncClient):
        confirm_resp = await client.post(
            "/api/agents/chat/confirm",
            json={},
        )
        assert confirm_resp.status_code == 400
        assert confirm_resp.json()["code"] == "missing_draft_id"

    async def test_confirm_invalid_contract_rejected(self, client: AsyncClient):
        """Draft com contrato inválido é rejeitado na confirmação."""
        # Create a draft with invalid contract via a special LLM.
        invalid_llm = MockInvalidContractLLM()
        with patch("app.api.agent_chat.resolve_llm_client", new=AsyncMock(return_value=invalid_llm)):
            resp = await client.post(
                "/api/agents/chat",
                json={"message": "Quero um agente"},
            )
        events = _parse_sse_events(resp.text)
        draft_id = [e for e in events if e["type"] == "done"][0]["data"]["draftId"]

        # Confirm should fail with 400 invalid_graph.
        confirm_resp = await client.post(
            "/api/agents/chat/confirm",
            json={"draftId": draft_id},
        )
        assert confirm_resp.status_code == 400
        assert confirm_resp.json()["code"] == "invalid_graph"

    async def test_confirm_draft_owner_isolation(
        self, client: AsyncClient, session: AsyncSession, second_user: User
    ):
        """Usuário B não pode confirmar draft do usuário A."""
        # User A creates a draft.
        resp = await client.post(
            "/api/agents/chat",
            json={"message": "Quero um agente"},
        )
        events = _parse_sse_events(resp.text)
        draft_id = [e for e in events if e["type"] == "done"][0]["data"]["draftId"]

        # Directly test the draft_store isolation.
        draft = await draft_store.get(session, draft_id, str(second_user.id))
        assert draft is None  # Owner isolation: second user can't access.


# ---------------------------------------------------------------------------
# Tests: Edit chat (owner isolation)
# ---------------------------------------------------------------------------


class TestEditChat:
    """Testa o chat de edição de agente existente."""

    async def test_edit_chat_streaming(self, client: AsyncClient, existing_agent: Agent):
        response = await client.post(
            f"/api/agents/{existing_agent.id}/chat",
            json={"message": "Adicione integração com GitHub"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse_events(response.text)
        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) == 1

    async def test_edit_chat_owner_isolation(
        self,
        client: AsyncClient,
        session: AsyncSession,
        second_user: User,
        existing_agent: Agent,
    ):
        """Usuário B não pode editar agente do usuário A."""
        from app.api.agent_chat import router as chat_router

        # We need a separate app with second_user as the current user.
        app2 = FastAPI()
        register_exception_handlers(app2)
        from app.api.agents import router as agents_router
        app2.include_router(agents_router, prefix="/api")
        app2.include_router(chat_router, prefix="/api")

        async def override_get_db2():
            yield session

        async def override_get_current_user2():
            return second_user

        app2.dependency_overrides[get_db] = override_get_db2
        app2.dependency_overrides[get_current_user] = override_get_current_user2

        mock_llm = MockChatLLM()
        with patch("app.api.agent_chat.resolve_llm_client", new=AsyncMock(return_value=mock_llm)), \
             patch("app.api.agent_chat.AgentService") as mock_service_cls:
            service = AgentService(storage=MockAgentStorage())
            mock_service_cls.return_value = service

            transport = ASGITransport(app=app2)
            async with AsyncClient(transport=transport, base_url="http://test") as c2:
                response = await c2.post(
                    f"/api/agents/{existing_agent.id}/chat",
                    json={"message": "Edite este agente"},
                )
                # Should be 404 (agent not found for this owner).
                assert response.status_code == 404
                assert response.json()["code"] == "agent_not_found"

    async def test_edit_chat_not_found(self, client: AsyncClient):
        response = await client.post(
            f"/api/agents/{uuid.uuid4()}/chat",
            json={"message": "Edite"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "agent_not_found"


# ---------------------------------------------------------------------------
# Tests: Rate limit (429)
# ---------------------------------------------------------------------------


class TestRateLimit:
    """Testa o rate limit do chat (30 req/min por usuário)."""

    async def test_rate_limit_429(self, client: AsyncClient):
        """31ª request no mesmo minuto deve retornar 429."""
        from app.api.agent_chat import chat_rate_limiter

        # Reset the rate limiter.
        chat_rate_limiter.cleanup()

        # Make 30 requests (all should succeed).
        for i in range(30):
            resp = await client.post(
                "/api/agents/chat",
                json={"message": f"Message {i}"},
            )
            assert resp.status_code == 200, f"Request {i} should succeed"

        # 31st request should be rate limited.
        resp = await client.post(
            "/api/agents/chat",
            json={"message": "One too many"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"] == "rate_limited"
        assert data["code"] == "rate_limited"
        assert "retryAfter" in data["details"]
        assert data["details"]["retryAfter"] > 0

    async def test_rate_limit_edit_chat(self, client: AsyncClient, existing_agent: Agent):
        """Rate limit também aplica ao chat de edição."""
        from app.api.agent_chat import chat_rate_limiter

        chat_rate_limiter.cleanup()

        for i in range(30):
            resp = await client.post(
                f"/api/agents/{existing_agent.id}/chat",
                json={"message": f"Edit {i}"},
            )
            assert resp.status_code == 200

        resp = await client.post(
            f"/api/agents/{existing_agent.id}/chat",
            json={"message": "Too many"},
        )
        assert resp.status_code == 429
        assert resp.json()["code"] == "rate_limited"


# ---------------------------------------------------------------------------
# Tests: Validation errors in stream
# ---------------------------------------------------------------------------


class TestValidationInStream:
    """Testa que erros de validação aparecem no stream SSE."""

    async def test_invalid_contract_in_stream(self, client: AsyncClient):
        """LLM retorna contrato inválido: validation_error event no stream."""
        invalid_llm = MockInvalidContractLLM()
        with patch("app.api.agent_chat.resolve_llm_client", new=AsyncMock(return_value=invalid_llm)):
            response = await client.post(
                "/api/agents/chat",
                json={"message": "Quero um agente"},
            )
        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        validation_events = [e for e in events if e["type"] == "validation_error"]
        assert len(validation_events) == 1
        assert len(validation_events[0]["data"]) >= 1  # At least one error message


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_sse_events(raw: str) -> list[dict]:
    """Parsa eventos SSE do formato 'data: {json}

'."""
    events = []
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[6:]
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events
