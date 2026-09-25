"""Tests for the skill loader (D8, spec 6.6).

Dono: pe-loader (FASE 4). Cobre:
- cache local de skills (TTL + hit/miss);
- toolFilter do MCP;
- shellAccess=false (shell ausente) vs true (shell presente);
- MCP indisponível (falha parcial não derruba o load);
- skills built-in vs custom (Garage);
- knowledge via RAG (delimitado por EXTERNAL_DATA);
- AgentCapabilities JSON-serializável.

Garage, MCP e embedder são mockados; o DB usa o banco de teste isolado
(conftest.py).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentCapabilities, AgentSnapshot
from app.db.models import CustomTool, MCPServer, User
from app.knowledge.rag import RagService
from app.skills.loader import (
    LoadResult,
    SkillContentCache,
    SkillLoader,
    load,
)
from app.skills.storage import SkillStorage

# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------


def _make_snapshot(
    *,
    agent_id: str = "agent-1",
    prompt: str = "You are a helpful agent.",
    shell_access: bool = False,
    skills: list[dict] | None = None,
    tools: list[dict] | None = None,
    mcp_servers: list[dict] | None = None,
    knowledge: list[dict] | None = None,
) -> AgentSnapshot:
    return AgentSnapshot(
        id=agent_id,
        name="Test Agent",
        type="developer",
        description="test",
        prompt=prompt,
        strategy="",
        model="gpt-4o",
        max_iterations=5,
        timeout=60,
        shell_access=shell_access,
        skills=skills or [],
        tools=tools or [],
        mcp_servers=mcp_servers or [],
        knowledge=knowledge or [],
        inputs=[],
        outputs=[{"name": "output", "type": "string", "required": True}],
        actions=["follow", "finalize"],
    )


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Mock do SkillStorage (Garage)."""
    storage = AsyncMock(spec=SkillStorage)
    storage.get_skill = AsyncMock(return_value="# Custom Skill\n\nDo the thing.")
    storage.save_skill = AsyncMock()
    storage.delete_skill = AsyncMock()
    return storage


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="loader@example.com",
        name="Loader User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
def owner_id(test_user: User) -> uuid.UUID:
    return test_user.id


class _FakeMCPClient:
    """Client MCP fake: controla o resultado de connect/list_tools."""

    def __init__(
        self,
        tools: list[dict] | None = None,
        connect_error: Exception | None = None,
    ) -> None:
        self._tools = tools or []
        self._connect_error = connect_error
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        if self._connect_error is not None:
            raise self._connect_error
        self.connected = True

    async def list_tools(self) -> list[dict]:
        return self._tools

    async def disconnect(self) -> None:
        self.disconnected = True


def _make_loader(
    session: AsyncSession,
    storage: AsyncMock,
    *,
    rag: RagService | None = None,
    mcp_factory=None,
    cache: SkillContentCache | None = None,
) -> SkillLoader:
    return SkillLoader(
        db=session,
        storage=storage,
        rag=rag,
        mcp_client_factory=mcp_factory,
        cache=cache or SkillContentCache(),
    )


# ---------------------------------------------------------------------------
# Tests: system prompt + skills
# ---------------------------------------------------------------------------


class TestSkills:
    @pytest.mark.asyncio
    async def test_base_prompt_in_system_prompt(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot(prompt="BASE PROMPT"))
        assert "BASE PROMPT" in result.capabilities.system_prompt

    @pytest.mark.asyncio
    async def test_builtin_skill_injected(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        # "code-gen" é uma skill built-in: resolvida em memória, sem Garage.
        loader = _make_loader(session, mock_storage)
        result = await loader.load(
            _make_snapshot(skills=[{"skillId": "code-gen"}])
        )
        assert "## Skill: code-gen" in result.capabilities.system_prompt
        # Built-in não consulta o storage.
        mock_storage.get_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_skill_from_garage(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        skill_id = str(uuid.uuid4())
        mock_storage.get_skill = AsyncMock(return_value="# My Skill\n\nCustom content.")
        loader = _make_loader(session, mock_storage)
        result = await loader.load(
            _make_snapshot(skills=[{"skillId": skill_id, "name": "My Skill"}])
        )
        assert "## Skill: My Skill" in result.capabilities.system_prompt
        assert "Custom content." in result.capabilities.system_prompt
        mock_storage.get_skill.assert_awaited_once_with(skill_id)

    @pytest.mark.asyncio
    async def test_skill_missing_in_garage_is_partial_failure(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        skill_id = str(uuid.uuid4())
        mock_storage.get_skill = AsyncMock(side_effect=Exception("not found"))
        loader = _make_loader(session, mock_storage)
        result = await loader.load(
            _make_snapshot(prompt="BASE", skills=[{"skillId": skill_id}])
        )
        # Falha parcial: o load segue, o prompt base permanece, e há um aviso.
        assert "BASE" in result.capabilities.system_prompt
        assert len(result.warnings) == 1
        assert skill_id in result.warnings[0]

    @pytest.mark.asyncio
    async def test_skill_ref_without_id_ignored(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot(skills=[{"name": "no-id"}]))
        assert len(result.warnings) == 1


# ---------------------------------------------------------------------------
# Tests: cache local de skills
# ---------------------------------------------------------------------------


class TestSkillCache:
    @pytest.mark.asyncio
    async def test_cache_hit_avoids_second_download(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        skill_id = str(uuid.uuid4())
        mock_storage.get_skill = AsyncMock(return_value="cached content")
        cache = SkillContentCache()
        loader = _make_loader(session, mock_storage, cache=cache)

        await loader.load(_make_snapshot(skills=[{"skillId": skill_id}]))
        await loader.load(_make_snapshot(skills=[{"skillId": skill_id}]))

        # Só um download do Garage (o segundo load usa o cache).
        assert mock_storage.get_skill.await_count == 1

    def test_cache_ttl_expiry(self) -> None:
        cache = SkillContentCache(ttl_seconds=0.0)  # TTL zero: expira na hora.
        cache.put("s1", "content")
        # Com TTL 0, o próximo get já está expirado.
        assert cache.get("s1") is None

    def test_cache_miss_returns_none(self) -> None:
        cache = SkillContentCache()
        assert cache.get("missing") is None


# ---------------------------------------------------------------------------
# Tests: tools (básicas + custom + shellAccess)
# ---------------------------------------------------------------------------


class TestTools:
    @pytest.mark.asyncio
    async def test_builtin_tools_present_without_shell(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot(shell_access=False))
        names = {t["name"] for t in result.capabilities.tools}
        assert "read_file" in names
        assert "web_search" in names
        # shell é opt-in: ausente quando shellAccess=false.
        assert "shell" not in names

    @pytest.mark.asyncio
    async def test_shell_present_when_shell_access_true(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot(shell_access=True))
        names = {t["name"] for t in result.capabilities.tools}
        assert "shell" in names

    @pytest.mark.asyncio
    async def test_custom_tool_deployed_included(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        tool = CustomTool(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name="consultar_jira",
            description="Consulta o Jira",
            category="custom",
            script="async def execute(args): return {}",
            io={
                "inputs": [
                    {"name": "query", "type": "string", "required": True},
                    {"name": "limit", "type": "integer", "required": False},
                ],
                "outputs": [{"name": "results", "type": "array"}],
            },
            version=2,
            status="deployed",
        )
        session.add(tool)
        await session.commit()

        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot(tools=[{"toolId": str(tool.id)}]))

        custom = [t for t in result.capabilities.tools if t["source"] == "custom"]
        assert len(custom) == 1
        assert custom[0]["name"] == "consultar_jira"
        assert custom[0]["inputSchema"]["properties"]["query"]["type"] == "string"
        assert custom[0]["inputSchema"]["required"] == ["query"]
        assert custom[0]["version"] == 2

    @pytest.mark.asyncio
    async def test_custom_tool_not_deployed_excluded(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        tool = CustomTool(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name="draft_tool",
            description="draft",
            category="custom",
            script="async def execute(args): return {}",
            io={"inputs": [], "outputs": []},
            version=1,
            status="draft",
        )
        session.add(tool)
        await session.commit()

        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot(tools=[{"toolId": str(tool.id)}]))

        custom = [t for t in result.capabilities.tools if t["source"] == "custom"]
        assert custom == []
        assert any("não está deployada" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_custom_tool_missing_is_partial_failure(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        missing_id = str(uuid.uuid4())
        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot(tools=[{"toolId": missing_id}]))
        assert any(missing_id in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Tests: MCP servers
# ---------------------------------------------------------------------------


class TestMCP:
    @pytest.mark.asyncio
    async def test_mcp_tools_discovered(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        server = MCPServer(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name="jira-mcp",
            description="Jira MCP",
            transport="http",
            url="http://mcp:9000",
            env={},
            status="connected",
            discovered_tools=[],
        )
        session.add(server)
        await session.commit()

        fake = _FakeMCPClient(
            tools=[
                {"name": "create_issue", "description": "Cria issue", "inputSchema": {}},
                {"name": "list_issues", "description": "Lista issues", "inputSchema": {}},
            ]
        )
        loader = _make_loader(
            session, mock_storage, mcp_factory=lambda **kw: fake
        )
        result = await loader.load(
            _make_snapshot(mcp_servers=[{"serverId": str(server.id)}])
        )

        mcp_names = {t["name"] for t in result.capabilities.mcp_tools}
        assert "jira-mcp__create_issue" in mcp_names
        assert "jira-mcp__list_issues" in mcp_names
        assert fake.connected is True
        assert fake.disconnected is True

    @pytest.mark.asyncio
    async def test_mcp_tool_filter_applied(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        server = MCPServer(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name="jira-mcp",
            description="Jira MCP",
            transport="http",
            url="http://mcp:9000",
            env={},
            status="connected",
            discovered_tools=[],
        )
        session.add(server)
        await session.commit()

        fake = _FakeMCPClient(
            tools=[
                {"name": "create_issue", "description": "", "inputSchema": {}},
                {"name": "list_issues", "description": "", "inputSchema": {}},
            ]
        )
        loader = _make_loader(session, mock_storage, mcp_factory=lambda **kw: fake)
        result = await loader.load(
            _make_snapshot(
                mcp_servers=[
                    {"serverId": str(server.id), "toolFilter": ["list_issues"]}
                ]
            )
        )

        mcp_names = {t["name"] for t in result.capabilities.mcp_tools}
        assert "jira-mcp__list_issues" in mcp_names
        assert "jira-mcp__create_issue" not in mcp_names

    @pytest.mark.asyncio
    async def test_mcp_unavailable_is_partial_failure(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        server = MCPServer(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name="down-mcp",
            description="Fora do ar",
            transport="http",
            url="http://down:9000",
            env={},
            status="disconnected",
            discovered_tools=[],
        )
        session.add(server)
        await session.commit()

        fake = _FakeMCPClient(connect_error=ConnectionError("refused"))
        loader = _make_loader(session, mock_storage, mcp_factory=lambda **kw: fake)
        result = await loader.load(
            _make_snapshot(
                prompt="BASE", mcp_servers=[{"serverId": str(server.id)}]
            )
        )

        # Falha parcial: o load segue, sem tools MCP, com aviso.
        assert result.capabilities.mcp_tools == []
        assert "BASE" in result.capabilities.system_prompt
        assert any("down-mcp" in w or str(server.id) in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_mcp_server_missing_is_partial_failure(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        missing_id = str(uuid.uuid4())
        loader = _make_loader(session, mock_storage)
        result = await loader.load(
            _make_snapshot(mcp_servers=[{"serverId": missing_id}])
        )
        assert result.capabilities.mcp_tools == []
        assert any(missing_id in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Tests: knowledge (RAG)
# ---------------------------------------------------------------------------


class TestKnowledge:
    @pytest.mark.asyncio
    async def test_knowledge_context_wrapped_external_data(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        # RAG mockado: retorna chunks fixos.
        rag = AsyncMock(spec=RagService)
        rag.query = AsyncMock(
            return_value=[
                {"score": 0.9, "content": "chunk one", "knowledgeBaseId": "kb1",
                 "documentId": None, "chunkIndex": 0},
                {"score": 0.8, "content": "chunk two", "knowledgeBaseId": "kb1",
                 "documentId": None, "chunkIndex": 1},
            ]
        )
        loader = _make_loader(session, mock_storage, rag=rag)
        kb_id = str(uuid.uuid4())
        result = await loader.load(
            _make_snapshot(knowledge=[{"source": "upload", "reference": kb_id}])
        )

        assert len(result.capabilities.knowledge_context) == 2
        for block in result.capabilities.knowledge_context:
            assert block.startswith("<<<EXTERNAL_DATA>>>")
            assert block.endswith("<<<END_EXTERNAL_DATA>>>")
        assert "chunk one" in result.capabilities.knowledge_context[0]
        # A query RAG foi chamada com o id da KB.
        rag.query.assert_awaited_once()
        _, kwargs = rag.query.call_args
        assert uuid.UUID(kb_id) in kwargs["knowledge_base_ids"]

    @pytest.mark.asyncio
    async def test_knowledge_query_failure_is_partial(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        rag = AsyncMock(spec=RagService)
        rag.query = AsyncMock(side_effect=Exception("pgvector down"))
        loader = _make_loader(session, mock_storage, rag=rag)
        kb_id = str(uuid.uuid4())
        result = await loader.load(
            _make_snapshot(prompt="BASE", knowledge=[{"reference": kb_id}])
        )
        assert result.capabilities.knowledge_context == []
        assert "BASE" in result.capabilities.system_prompt
        assert any("knowledge query falhou" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_no_knowledge_refs_returns_empty(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot())
        assert result.capabilities.knowledge_context == []


# ---------------------------------------------------------------------------
# Tests: contrato + serialização
# ---------------------------------------------------------------------------


class TestContract:
    @pytest.mark.asyncio
    async def test_returns_load_result_with_capabilities(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        loader = _make_loader(session, mock_storage)
        result = await loader.load(_make_snapshot())
        assert isinstance(result, LoadResult)
        assert isinstance(result.capabilities, AgentCapabilities)

    @pytest.mark.asyncio
    async def test_capabilities_json_serializable(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        # Mochila completa: skills + tools + mcp + knowledge.
        tool = CustomTool(
            id=uuid.uuid4(), owner_id=owner_id, name="t", description="d",
            category="custom", script="async def execute(a): return {}",
            io={"inputs": [{"name": "x", "type": "string", "required": True}],
                "outputs": []},
            version=1, status="deployed",
        )
        server = MCPServer(
            id=uuid.uuid4(), owner_id=owner_id, name="srv", description="d",
            transport="http", url="http://mcp:9000", env={},
            status="connected", discovered_tools=[],
        )
        session.add_all([tool, server])
        await session.commit()

        fake = _FakeMCPClient(tools=[{"name": "op", "description": "", "inputSchema": {}}])
        rag = AsyncMock(spec=RagService)
        rag.query = AsyncMock(return_value=[
            {"score": 0.9, "content": "k", "knowledgeBaseId": "kb",
             "documentId": None, "chunkIndex": 0}
        ])
        loader = _make_loader(
            session, mock_storage, rag=rag, mcp_factory=lambda **kw: fake
        )
        result = await loader.load(
            _make_snapshot(
                skills=[{"skillId": "code-gen"}],
                tools=[{"toolId": str(tool.id)}],
                mcp_servers=[{"serverId": str(server.id)}],
                knowledge=[{"reference": str(uuid.uuid4())}],
            )
        )

        # Round-trip JSON: o objeto trafega na request para o worker.
        payload = json.loads(json.dumps(result.capabilities.__dict__))
        assert payload["system_prompt"]
        assert isinstance(payload["tools"], list)
        assert isinstance(payload["mcp_tools"], list)
        assert isinstance(payload["knowledge_context"], list)

    @pytest.mark.asyncio
    async def test_convenience_load_function(
        self, session: AsyncSession, mock_storage: AsyncMock
    ) -> None:
        result = await load(_make_snapshot(), session, mock_storage)
        assert isinstance(result, LoadResult)
        assert "You are a helpful agent." in result.capabilities.system_prompt
