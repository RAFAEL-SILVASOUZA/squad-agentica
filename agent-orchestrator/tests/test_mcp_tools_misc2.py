"""Testes das ferramentas MCP de Knowledge, Skills, Tools, Workspaces e
Approvals (23 tools).

Cobre: create, list, get, update, delete + operações especiais (upload,
query, approve/reject) + erro de autenticação (sem usuário no contextvar) +
ID inválido. As tools são funções async decoradas com ``@mcp.tool()``; nos
testes são chamadas diretamente como funções async.

Setup (mesmo padrão de test_mcp_tools_misc.py):
- ``get_current_mcp_user`` é patcheado para retornar o usuário de teste.
- ``async_session_factory`` é patcheado para usar a sessão do banco de teste.
- Storage (Garage), RAG (embedder) e WorkspaceManager são patcheados para
  evitar dependência de rede/disco.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import MockEmbedder
from app.db.models import (
    ApprovalRequest,
    CustomTool,
    KnowledgeBase,
    Pipeline,
    PipelineRun,
    Skill,
    User,
)
from app.mcp_server.tools import ToolError

TEST_DIM = 1536


# ---------------------------------------------------------------------------
# Mocks de storage / RAG / workspace
# ---------------------------------------------------------------------------


class MockKnowledgeStorage:
    """Mock in-memory do KnowledgeStorage (Garage)."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    async def save_document(self, kb_id: str, doc_id: str, data: bytes, ext: str = "") -> str:
        key = f"{kb_id}/{doc_id}.{ext}" if ext else f"{kb_id}/{doc_id}"
        self.store[key] = data
        return key

    async def get_document(self, kb_id: str, doc_id: str, ext: str = "") -> bytes:
        key = f"{kb_id}/{doc_id}.{ext}" if ext else f"{kb_id}/{doc_id}"
        return self.store[key]

    async def delete_document(self, kb_id: str, doc_id: str, ext: str = "") -> None:
        key = f"{kb_id}/{doc_id}.{ext}" if ext else f"{kb_id}/{doc_id}"
        self.store.pop(key, None)


class MockSkillStorage:
    """Mock in-memory do SkillStorage (Garage)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def save_skill(self, skill_id: str, content_md: str) -> None:
        self.store[skill_id] = content_md

    async def get_skill(self, skill_id: str) -> str:
        return self.store[skill_id]

    async def delete_skill(self, skill_id: str) -> None:
        self.store.pop(skill_id, None)


def _mock_ws_manager(tmp_path: Path) -> MagicMock:
    """WorkspaceManager mock que aponta para ``tmp_path`` (disco real)."""
    from app.runtime.workspace import WorkspaceManager

    return WorkspaceManager(tmp_path / "workspaces")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def knowledge_env(session: AsyncSession, test_user: User, tmp_path: Path):
    """Ambiente para as tools de knowledge."""
    storage = MockKnowledgeStorage()
    mock_embedder = MockEmbedder(dim=TEST_DIM)

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.knowledge.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.knowledge.async_session_factory",
            fake_session_factory,
        ),
        patch(
            "app.mcp_server.tools.knowledge.get_knowledge_storage",
            return_value=storage,
        ),
        patch(
            "app.mcp_server.tools.knowledge.resolve_embedder",
            new_callable=AsyncMock,
            return_value=mock_embedder,
        ),
    ):
        yield test_user


@pytest_asyncio.fixture
async def skills_env(session: AsyncSession, test_user: User):
    """Ambiente para as tools de skills."""
    storage = MockSkillStorage()

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.skills.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.skills.async_session_factory",
            fake_session_factory,
        ),
        patch(
            "app.mcp_server.tools.skills.get_skill_storage",
            return_value=storage,
        ),
    ):
        yield test_user


@pytest_asyncio.fixture
async def tools_env(session: AsyncSession, test_user: User):
    """Ambiente para as tools de tools custom."""

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.tools.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.tools.async_session_factory",
            fake_session_factory,
        ),
    ):
        yield test_user


@pytest_asyncio.fixture
async def workspaces_env(session: AsyncSession, test_user: User, tmp_path: Path):
    """Ambiente para as tools de workspaces."""

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.workspaces.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.workspaces.async_session_factory",
            fake_session_factory,
        ),
        patch(
            "app.mcp_server.tools.workspaces.WorkspaceManager",
            lambda: _mock_ws_manager(tmp_path),
        ),
    ):
        yield test_user


@pytest_asyncio.fixture
async def approvals_env(session: AsyncSession, test_user: User):
    """Ambiente para as tools de approvals."""

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.approvals.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.approvals.async_session_factory",
            fake_session_factory,
        ),
        patch(
            "app.mcp_server.tools.approvals.ws_publish",
            new_callable=AsyncMock,
        ),
        patch(
            "app.mcp_server.tools.approvals._trigger_resume",
            new_callable=AsyncMock,
        ),
    ):
        yield test_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_run(session: AsyncSession, owner_id: uuid.UUID) -> PipelineRun:
    """Cria uma pipeline + run (completed) do usuário."""
    pipeline = Pipeline(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=f"Pipeline de teste {uuid.uuid4().hex[:8]}",
        description="",
        status="completed",
        entry_node_id=uuid.uuid4(),
    )
    session.add(pipeline)
    await session.flush()
    run = PipelineRun(
        id=uuid.uuid4(),
        owner_id=owner_id,
        pipeline_id=pipeline.id,
        thread_id=f"{pipeline.id}:r",
        status="completed",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def _make_approval(
    session: AsyncSession,
    owner_id: uuid.UUID,
    status: str = "pending",
    run: PipelineRun | None = None,
) -> ApprovalRequest:
    """Cria uma ApprovalRequest do usuário."""
    approval = ApprovalRequest(
        id=uuid.uuid4(),
        owner_id=owner_id,
        pipeline_id=uuid.uuid4(),
        run_id=run.id if run else None,
        node_id="node-1",
        checkpoint_id="ckpt-1",
        message="Aprovar?",
        context={},
        status=status,
        channel="in-app",
    )
    session.add(approval)
    await session.commit()
    await session.refresh(approval)
    return approval


# ===========================================================================
# KNOWLEDGE (6 tools)
# ===========================================================================


class TestCreateKnowledgeBase:
    async def test_create_global(self, knowledge_env: User):
        """create_knowledge_base com scope global cria a KB."""
        from app.mcp_server.tools.knowledge import create_knowledge_base

        result = await create_knowledge_base(name="KB Global", scope="global", source="upload")
        assert result["name"] == "KB Global"
        assert result["scope"] == "global"
        assert result["source"] == "upload"
        assert result["documentCount"] == 0
        assert result["id"] is not None

    async def test_create_agent_scope(self, knowledge_env: User):
        """create_knowledge_base com scope agent + scopeRef cria a KB."""
        from app.mcp_server.tools.knowledge import create_knowledge_base

        result = await create_knowledge_base(
            name="KB Agent", scope="agent", scope_ref="agent-123", source="upload"
        )
        assert result["scope"] == "agent"
        assert result["scopeRef"] == "agent-123"

    async def test_create_agent_scope_missing_ref(self, knowledge_env: User):
        """create_knowledge_base com scope agent sem scopeRef lança ToolError."""
        from app.mcp_server.tools.knowledge import create_knowledge_base

        with pytest.raises(ToolError) as exc_info:
            await create_knowledge_base(name="KB Sem Ref", scope="agent", source="upload")
        assert "scope" in exc_info.value.message.lower()

    async def test_create_duplicate_name(self, knowledge_env: User):
        """create_knowledge_base com nome duplicado lança ToolError."""
        from app.mcp_server.tools.knowledge import create_knowledge_base

        await create_knowledge_base(name="Dup KB", scope="global", source="upload")
        with pytest.raises(ToolError) as exc_info:
            await create_knowledge_base(name="Dup KB", scope="global", source="upload")
        assert "Erro ao criar" in exc_info.value.message

    async def test_create_invalid_source(self, knowledge_env: User):
        """create_knowledge_base com source inválido lança ToolError."""
        from app.mcp_server.tools.knowledge import create_knowledge_base

        with pytest.raises(ToolError):
            await create_knowledge_base(name="KB Bad", scope="global", source="invalid")


class TestListKnowledgeBases:
    async def test_list_empty(self, knowledge_env: User):
        """list_knowledge_bases sem KBs retorna lista vazia."""
        from app.mcp_server.tools.knowledge import list_knowledge_bases

        result = await list_knowledge_bases()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 20

    async def test_list_with_items(self, knowledge_env: User):
        """list_knowledge_bases retorna as KBs criadas."""
        from app.mcp_server.tools.knowledge import create_knowledge_base, list_knowledge_bases

        await create_knowledge_base(name="KB1", scope="global", source="upload")
        await create_knowledge_base(name="KB2", scope="global", source="url")
        result = await list_knowledge_bases()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_filter_by_scope(self, knowledge_env: User):
        """list_knowledge_bases com filtro de scope."""
        from app.mcp_server.tools.knowledge import create_knowledge_base, list_knowledge_bases

        await create_knowledge_base(name="KBG", scope="global", source="upload")
        await create_knowledge_base(
            name="KBA", scope="agent", scope_ref="a1", source="upload"
        )
        result = await list_knowledge_bases(scope="global")
        assert result["total"] == 1
        assert result["items"][0]["name"] == "KBG"


class TestGetKnowledgeBase:
    async def test_get_success(self, knowledge_env: User):
        """get_knowledge_base com id válido retorna a KB."""
        from app.mcp_server.tools.knowledge import create_knowledge_base, get_knowledge_base

        created = await create_knowledge_base(name="Get KB", scope="global", source="upload")
        result = await get_knowledge_base(created["id"])
        assert result["id"] == created["id"]
        assert result["name"] == "Get KB"

    async def test_get_not_found(self, knowledge_env: User):
        """get_knowledge_base com id inexistente lança ToolError."""
        from app.mcp_server.tools.knowledge import get_knowledge_base

        with pytest.raises(ToolError) as exc_info:
            await get_knowledge_base(str(uuid.uuid4()))
        assert "não encontrado" in exc_info.value.message

    async def test_get_invalid_id(self, knowledge_env: User):
        """get_knowledge_base com id inválido lança ToolError."""
        from app.mcp_server.tools.knowledge import get_knowledge_base

        with pytest.raises(ToolError) as exc_info:
            await get_knowledge_base("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestDeleteKnowledgeBase:
    async def test_delete_success(self, knowledge_env: User):
        """delete_knowledge_base remove a KB."""
        from app.mcp_server.tools.knowledge import (
            create_knowledge_base,
            delete_knowledge_base,
            get_knowledge_base,
        )

        created = await create_knowledge_base(name="Del KB", scope="global", source="upload")
        result = await delete_knowledge_base(created["id"])
        assert result["deleted"] is True
        assert result["id"] == created["id"]
        with pytest.raises(ToolError):
            await get_knowledge_base(created["id"])

    async def test_delete_not_found(self, knowledge_env: User):
        """delete_knowledge_base com id inexistente lança ToolError."""
        from app.mcp_server.tools.knowledge import delete_knowledge_base

        with pytest.raises(ToolError):
            await delete_knowledge_base(str(uuid.uuid4()))


class TestUploadKnowledgeFile:
    async def test_upload_txt(self, knowledge_env: User):
        """upload_knowledge_file com .txt cria o documento e ingere."""
        from app.mcp_server.tools.knowledge import create_knowledge_base, upload_knowledge_file

        kb = await create_knowledge_base(name="Up KB", scope="global", source="upload")
        result = await upload_knowledge_file(
            knowledge_base_id=kb["id"],
            file_name="doc.txt",
            content="conteúdo do documento " * 50,
        )
        assert result["name"] == "doc.txt"
        assert result["status"] == "ready"
        assert result["chunkCount"] >= 1
        assert result["documentId"] is not None

    async def test_upload_invalid_extension(self, knowledge_env: User):
        """upload_knowledge_file com extensão inválida lança ToolError."""
        from app.mcp_server.tools.knowledge import create_knowledge_base, upload_knowledge_file

        kb = await create_knowledge_base(name="Up KB2", scope="global", source="upload")
        with pytest.raises(ToolError) as exc_info:
            await upload_knowledge_file(
                knowledge_base_id=kb["id"], file_name="malware.exe", content="x"
            )
        assert "tipo de arquivo" in exc_info.value.message.lower() or "inválido" in exc_info.value.message.lower()

    async def test_upload_not_found(self, knowledge_env: User):
        """upload_knowledge_file com KB inexistente lança ToolError."""
        from app.mcp_server.tools.knowledge import upload_knowledge_file

        with pytest.raises(ToolError):
            await upload_knowledge_file(
                knowledge_base_id=str(uuid.uuid4()), file_name="doc.txt", content="x"
            )


class TestQueryKnowledge:
    async def test_query_with_results(self, knowledge_env: User):
        """query_knowledge retorna chunks relevantes."""
        from app.mcp_server.tools.knowledge import (
            create_knowledge_base,
            query_knowledge,
            upload_knowledge_file,
        )

        kb = await create_knowledge_base(
            name="Q KB", scope="global", source="upload", similarity_threshold=-1.0
        )
        await upload_knowledge_file(
            knowledge_base_id=kb["id"],
            file_name="d.txt",
            content="zebra zebra zebra zebra zebra " * 50,
        )
        result = await query_knowledge(
            query="zebra", knowledge_base_ids=[kb["id"]], top_k=3
        )
        assert "chunks" in result
        assert len(result["chunks"]) >= 1
        assert "zebra" in result["chunks"][0]["content"]

    async def test_query_no_kb_ids(self, knowledge_env: User):
        """query_knowledge sem KBs retorna lista vazia."""
        from app.mcp_server.tools.knowledge import query_knowledge

        result = await query_knowledge(query="x", knowledge_base_ids=[])
        assert result["chunks"] == []

    async def test_query_invalid_kb_id(self, knowledge_env: User):
        """query_knowledge com id de KB inválido lança ToolError."""
        from app.mcp_server.tools.knowledge import query_knowledge

        with pytest.raises(ToolError) as exc_info:
            await query_knowledge(query="x", knowledge_base_ids=["id-invalido"])
        assert "ID inválido" in exc_info.value.message


class TestKnowledgeAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession, tmp_path: Path):
        """Tool de knowledge sem usuário no contextvar lança ToolError."""
        from app.mcp_server.tools.knowledge import create_knowledge_base

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.knowledge.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.knowledge.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await create_knowledge_base(name="Sem auth", scope="global", source="upload")
            assert "Não autenticado" in exc_info.value.message


# ===========================================================================
# SKILLS (5 tools)
# ===========================================================================


class TestCreateSkill:
    async def test_create_skill(self, skills_env: User):
        """create_skill cria a skill."""
        from app.mcp_server.tools.skills import create_skill

        result = await create_skill(
            name="minha-skill",
            description="Descrição",
            category="code",
            definition={"template": "Faça {x}", "variables": ["x"]},
        )
        assert result["name"] == "minha-skill"
        assert result["category"] == "code"
        assert result["type"] == "prompt"
        assert result["id"] is not None

    async def test_create_duplicate_name(self, skills_env: User):
        """create_skill com nome duplicado lança ToolError."""
        from app.mcp_server.tools.skills import create_skill

        await create_skill(name="dup-skill", category="code", definition={"template": "x"})
        with pytest.raises(ToolError) as exc_info:
            await create_skill(name="dup-skill", category="code", definition={"template": "x"})
        assert "Erro ao criar" in exc_info.value.message

    async def test_create_invalid_category(self, skills_env: User):
        """create_skill com categoria inválida lança ToolError."""
        from app.mcp_server.tools.skills import create_skill

        with pytest.raises(ToolError):
            await create_skill(name="bad-cat", category="invalid", definition={"template": "x"})


class TestListSkills:
    async def test_list_empty(self, skills_env: User):
        """list_skills sem skills retorna lista vazia."""
        from app.mcp_server.tools.skills import list_skills

        result = await list_skills()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 50

    async def test_list_with_items(self, skills_env: User):
        """list_skills retorna as skills criadas."""
        from app.mcp_server.tools.skills import create_skill, list_skills

        await create_skill(name="s1", category="code", definition={"template": "x"})
        await create_skill(name="s2", category="docs", definition={"template": "y"})
        result = await list_skills()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_filter_by_category(self, skills_env: User):
        """list_skills com filtro de categoria."""
        from app.mcp_server.tools.skills import create_skill, list_skills

        await create_skill(name="s1", category="code", definition={"template": "x"})
        await create_skill(name="s2", category="docs", definition={"template": "y"})
        result = await list_skills(category="code")
        assert result["total"] == 1
        assert result["items"][0]["name"] == "s1"


class TestGetSkill:
    async def test_get_success(self, skills_env: User):
        """get_skill com id válido retorna a skill."""
        from app.mcp_server.tools.skills import create_skill, get_skill

        created = await create_skill(name="get-skill", category="code", definition={"template": "x"})
        result = await get_skill(created["id"])
        assert result["id"] == created["id"]
        assert result["name"] == "get-skill"

    async def test_get_not_found(self, skills_env: User):
        """get_skill com id inexistente lança ToolError."""
        from app.mcp_server.tools.skills import get_skill

        with pytest.raises(ToolError) as exc_info:
            await get_skill(str(uuid.uuid4()))
        assert "não encontrada" in exc_info.value.message

    async def test_get_invalid_id(self, skills_env: User):
        """get_skill com id inválido lança ToolError."""
        from app.mcp_server.tools.skills import get_skill

        with pytest.raises(ToolError) as exc_info:
            await get_skill("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestUpdateSkill:
    async def test_update_name(self, skills_env: User):
        """update_skill altera o nome."""
        from app.mcp_server.tools.skills import create_skill, update_skill

        created = await create_skill(name="original", category="code", definition={"template": "x"})
        result = await update_skill(created["id"], name="renomeado")
        assert result["name"] == "renomeado"

    async def test_update_definition(self, skills_env: User):
        """update_skill altera a definição."""
        from app.mcp_server.tools.skills import create_skill, update_skill

        created = await create_skill(name="upd-def", category="code", definition={"template": "x"})
        result = await update_skill(
            created["id"], definition={"template": "novo {y}", "variables": ["y"]}
        )
        assert result["definition"]["template"] == "novo {y}"

    async def test_update_not_found(self, skills_env: User):
        """update_skill com id inexistente lança ToolError."""
        from app.mcp_server.tools.skills import update_skill

        with pytest.raises(ToolError):
            await update_skill(str(uuid.uuid4()), name="X")

    async def test_update_no_fields(self, skills_env: User):
        """update_skill sem nenhum campo lança ToolError."""
        from app.mcp_server.tools.skills import create_skill, update_skill

        created = await create_skill(name="no-upd", category="code", definition={"template": "x"})
        with pytest.raises(ToolError):
            await update_skill(created["id"])


class TestDeleteSkill:
    async def test_delete_success(self, skills_env: User):
        """delete_skill remove a skill."""
        from app.mcp_server.tools.skills import create_skill, delete_skill, get_skill

        created = await create_skill(name="del-skill", category="code", definition={"template": "x"})
        result = await delete_skill(created["id"])
        assert result["deleted"] is True
        assert result["id"] == created["id"]
        with pytest.raises(ToolError):
            await get_skill(created["id"])

    async def test_delete_not_found(self, skills_env: User):
        """delete_skill com id inexistente lança ToolError."""
        from app.mcp_server.tools.skills import delete_skill

        with pytest.raises(ToolError):
            await delete_skill(str(uuid.uuid4()))


class TestSkillsAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession):
        """Tool de skill sem usuário no contextvar lança ToolError."""
        from app.mcp_server.tools.skills import create_skill

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.skills.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.skills.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await create_skill(name="sem-auth", category="code", definition={"template": "x"})
            assert "Não autenticado" in exc_info.value.message


# ===========================================================================
# TOOLS (5 tools)
# ===========================================================================


class TestCreateTool:
    async def test_create_tool(self, tools_env: User):
        """create_tool cria a tool custom (status=draft)."""
        from app.mcp_server.tools.tools import create_tool

        result = await create_tool(
            name="minha-tool",
            description="Descrição",
            script="def main(): return 1",
        )
        assert result["name"] == "minha-tool"
        assert result["status"] == "draft"
        assert result["version"] == 1
        assert result["id"] is not None

    async def test_create_duplicate_name(self, tools_env: User):
        """create_tool com nome duplicado lança ToolError."""
        from app.mcp_server.tools.tools import create_tool

        await create_tool(name="dup-tool", script="x")
        with pytest.raises(ToolError) as exc_info:
            await create_tool(name="dup-tool", script="x")
        assert "Erro ao criar" in exc_info.value.message

    async def test_create_with_io(self, tools_env: User):
        """create_tool com inputs/outputs persiste o io."""
        from app.mcp_server.tools.tools import create_tool

        result = await create_tool(
            name="io-tool",
            script="x",
            inputs=[{"name": "a", "type": "string", "required": True}],
            outputs=[{"name": "b", "type": "number"}],
        )
        assert result["inputs"][0]["name"] == "a"
        assert result["inputs"][0]["type"] == "string"
        assert result["inputs"][0]["required"] is True
        assert result["outputs"][0]["name"] == "b"
        assert result["outputs"][0]["type"] == "number"


class TestListTools:
    async def test_list_empty(self, tools_env: User):
        """list_tools sem tools retorna lista vazia."""
        from app.mcp_server.tools.tools import list_tools

        result = await list_tools()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 50

    async def test_list_with_items(self, tools_env: User):
        """list_tools retorna as tools criadas."""
        from app.mcp_server.tools.tools import create_tool, list_tools

        await create_tool(name="t1", script="x")
        await create_tool(name="t2", script="y")
        result = await list_tools()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_filter_by_status(self, tools_env: User):
        """list_tools com filtro de status."""
        from app.mcp_server.tools.tools import create_tool, list_tools

        await create_tool(name="t1", script="x")
        result = await list_tools(status="draft")
        assert result["total"] == 1
        assert result["items"][0]["name"] == "t1"


class TestGetTool:
    async def test_get_success(self, tools_env: User):
        """get_tool com id válido retorna a tool."""
        from app.mcp_server.tools.tools import create_tool, get_tool

        created = await create_tool(name="get-tool", script="x")
        result = await get_tool(created["id"])
        assert result["id"] == created["id"]
        assert result["name"] == "get-tool"

    async def test_get_not_found(self, tools_env: User):
        """get_tool com id inexistente lança ToolError."""
        from app.mcp_server.tools.tools import get_tool

        with pytest.raises(ToolError) as exc_info:
            await get_tool(str(uuid.uuid4()))
        assert "não encontrada" in exc_info.value.message

    async def test_get_invalid_id(self, tools_env: User):
        """get_tool com id inválido lança ToolError."""
        from app.mcp_server.tools.tools import get_tool

        with pytest.raises(ToolError) as exc_info:
            await get_tool("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestUpdateTool:
    async def test_update_name(self, tools_env: User):
        """update_tool altera o nome."""
        from app.mcp_server.tools.tools import create_tool, update_tool

        created = await create_tool(name="original", script="x")
        result = await update_tool(created["id"], name="renomeado")
        assert result["name"] == "renomeado"

    async def test_update_script_resets_status(self, tools_env: User):
        """update_tool com script novo reseta status para draft."""
        from app.mcp_server.tools.tools import create_tool, update_tool

        created = await create_tool(name="upd-script", script="x")
        # Simula deployed
        result = await update_tool(created["id"], script="novo script")
        assert result["status"] == "draft"

    async def test_update_not_found(self, tools_env: User):
        """update_tool com id inexistente lança ToolError."""
        from app.mcp_server.tools.tools import update_tool

        with pytest.raises(ToolError):
            await update_tool(str(uuid.uuid4()), name="X")

    async def test_update_no_fields(self, tools_env: User):
        """update_tool sem nenhum campo lança ToolError."""
        from app.mcp_server.tools.tools import create_tool, update_tool

        created = await create_tool(name="no-upd", script="x")
        with pytest.raises(ToolError):
            await update_tool(created["id"])


class TestDeleteTool:
    async def test_delete_success(self, tools_env: User):
        """delete_tool arquiva a tool (soft delete)."""
        from app.mcp_server.tools.tools import create_tool, delete_tool, get_tool

        created = await create_tool(name="del-tool", script="x")
        result = await delete_tool(created["id"])
        assert result["deleted"] is True
        assert result["id"] == created["id"]
        # Soft delete: a tool ainda existe, mas com status archived.
        fetched = await get_tool(created["id"])
        assert fetched["status"] == "archived"

    async def test_delete_not_found(self, tools_env: User):
        """delete_tool com id inexistente lança ToolError."""
        from app.mcp_server.tools.tools import delete_tool

        with pytest.raises(ToolError):
            await delete_tool(str(uuid.uuid4()))


class TestToolsAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession):
        """Tool de tool custom sem usuário no contextvar lança ToolError."""
        from app.mcp_server.tools.tools import create_tool

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.tools.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.tools.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await create_tool(name="sem-auth", script="x")
            assert "Não autenticado" in exc_info.value.message


# ===========================================================================
# WORKSPACES (3 tools)
# ===========================================================================


class TestListWorkspaces:
    async def test_list_empty(self, workspaces_env: User):
        """list_workspaces sem runs retorna lista vazia."""
        from app.mcp_server.tools.workspaces import list_workspaces

        result = await list_workspaces()
        assert result["items"] == []
        assert result["total"] == 0

    async def test_list_with_items(self, workspaces_env: User, session: AsyncSession):
        """list_workspaces retorna os runs do usuário."""
        from app.mcp_server.tools.workspaces import list_workspaces

        await _make_run(session, workspaces_env.id)
        await _make_run(session, workspaces_env.id)
        result = await list_workspaces()
        assert result["total"] == 2
        assert len(result["items"]) == 2


class TestGetWorkspace:
    async def test_get_success(self, workspaces_env: User, session: AsyncSession):
        """get_workspace com id válido retorna o workspace."""
        from app.mcp_server.tools.workspaces import get_workspace

        run = await _make_run(session, workspaces_env.id)
        result = await get_workspace(str(run.id))
        assert result["id"] == str(run.id)
        assert result["status"] == "completed"
        assert "files" in result

    async def test_get_not_found(self, workspaces_env: User):
        """get_workspace com id inexistente lança ToolError."""
        from app.mcp_server.tools.workspaces import get_workspace

        with pytest.raises(ToolError) as exc_info:
            await get_workspace(str(uuid.uuid4()))
        assert "não encontrado" in exc_info.value.message

    async def test_get_invalid_id(self, workspaces_env: User):
        """get_workspace com id inválido lança ToolError."""
        from app.mcp_server.tools.workspaces import get_workspace

        with pytest.raises(ToolError) as exc_info:
            await get_workspace("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestDeleteWorkspace:
    async def test_delete_success(self, workspaces_env: User, session: AsyncSession):
        """delete_workspace remove o workspace do run."""
        from app.mcp_server.tools.workspaces import delete_workspace

        run = await _make_run(session, workspaces_env.id)
        result = await delete_workspace(str(run.id))
        assert result["deleted"] is True
        assert result["id"] == str(run.id)

    async def test_delete_not_found(self, workspaces_env: User):
        """delete_workspace com id inexistente lança ToolError."""
        from app.mcp_server.tools.workspaces import delete_workspace

        with pytest.raises(ToolError):
            await delete_workspace(str(uuid.uuid4()))


class TestWorkspacesAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession, tmp_path: Path):
        """Tool de workspace sem usuário no contextvar lança ToolError."""
        from app.mcp_server.tools.workspaces import list_workspaces

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.workspaces.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.workspaces.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await list_workspaces()
            assert "Não autenticado" in exc_info.value.message


# ===========================================================================
# APPROVALS (4 tools)
# ===========================================================================


class TestListApprovals:
    async def test_list_empty(self, approvals_env: User):
        """list_approvals sem aprovações retorna lista vazia."""
        from app.mcp_server.tools.approvals import list_approvals

        result = await list_approvals()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 20

    async def test_list_with_items(self, approvals_env: User, session: AsyncSession):
        """list_approvals retorna as aprovações do usuário."""
        from app.mcp_server.tools.approvals import list_approvals

        await _make_approval(session, approvals_env.id)
        await _make_approval(session, approvals_env.id)
        result = await list_approvals()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_filter_by_status(self, approvals_env: User, session: AsyncSession):
        """list_approvals com filtro de status."""
        from app.mcp_server.tools.approvals import list_approvals

        await _make_approval(session, approvals_env.id, status="pending")
        await _make_approval(session, approvals_env.id, status="approved")
        result = await list_approvals(status="pending")
        assert result["total"] == 1
        assert result["items"][0]["status"] == "pending"


class TestGetApproval:
    async def test_get_success(self, approvals_env: User, session: AsyncSession):
        """get_approval com id válido retorna a aprovação."""
        from app.mcp_server.tools.approvals import get_approval

        approval = await _make_approval(session, approvals_env.id)
        result = await get_approval(str(approval.id))
        assert result["id"] == str(approval.id)
        assert result["status"] == "pending"

    async def test_get_not_found(self, approvals_env: User):
        """get_approval com id inexistente lança ToolError."""
        from app.mcp_server.tools.approvals import get_approval

        with pytest.raises(ToolError) as exc_info:
            await get_approval(str(uuid.uuid4()))
        assert "não encontrada" in exc_info.value.message

    async def test_get_invalid_id(self, approvals_env: User):
        """get_approval com id inválido lança ToolError."""
        from app.mcp_server.tools.approvals import get_approval

        with pytest.raises(ToolError) as exc_info:
            await get_approval("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestApprove:
    async def test_approve_success(self, approvals_env: User, session: AsyncSession):
        """approve aprova uma aprovação pendente."""
        from app.mcp_server.tools.approvals import approve, get_approval

        approval = await _make_approval(session, approvals_env.id, status="pending")
        result = await approve(str(approval.id))
        assert result["status"] == "approved"
        fetched = await get_approval(str(approval.id))
        assert fetched["status"] == "approved"

    async def test_approve_already_responded(self, approvals_env: User, session: AsyncSession):
        """approve em aprovação já respondida lança ToolError."""
        from app.mcp_server.tools.approvals import approve

        approval = await _make_approval(session, approvals_env.id, status="approved")
        with pytest.raises(ToolError):
            await approve(str(approval.id))

    async def test_approve_not_found(self, approvals_env: User):
        """approve com id inexistente lança ToolError."""
        from app.mcp_server.tools.approvals import approve

        with pytest.raises(ToolError):
            await approve(str(uuid.uuid4()))


class TestReject:
    async def test_reject_success(self, approvals_env: User, session: AsyncSession):
        """reject rejeita uma aprovação pendente."""
        from app.mcp_server.tools.approvals import get_approval, reject

        approval = await _make_approval(session, approvals_env.id, status="pending")
        result = await reject(str(approval.id), response="motivo da rejeição")
        assert result["status"] == "rejected"
        fetched = await get_approval(str(approval.id))
        assert fetched["status"] == "rejected"
        assert fetched["response"] == "motivo da rejeição"

    async def test_reject_already_responded(self, approvals_env: User, session: AsyncSession):
        """reject em aprovação já respondida lança ToolError."""
        from app.mcp_server.tools.approvals import reject

        approval = await _make_approval(session, approvals_env.id, status="rejected")
        with pytest.raises(ToolError):
            await reject(str(approval.id))

    async def test_reject_not_found(self, approvals_env: User):
        """reject com id inexistente lança ToolError."""
        from app.mcp_server.tools.approvals import reject

        with pytest.raises(ToolError):
            await reject(str(uuid.uuid4()))


class TestApprovalsAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession):
        """Tool de approval sem usuário no contextvar lança ToolError."""
        from app.mcp_server.tools.approvals import list_approvals

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.approvals.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.approvals.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await list_approvals()
            assert "Não autenticado" in exc_info.value.message
