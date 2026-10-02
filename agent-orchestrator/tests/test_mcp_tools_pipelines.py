"""Testes das ferramentas MCP de pipelines e runs (Task 7).

Cobre:
- pipelines: create, list, get, update, delete, validate
- runs: list_runs, get_run (run_pipeline e cancel_run exigem executor +
  workspace, então testamos apenas o erro de autenticação)
- Erro de autenticação (sem usuário no contextvar)
- ID inválido (_parse_uuid lança ToolError)

Setup:
- ``get_current_mcp_user`` é patcheado para retornar o usuário de teste.
- ``async_session_factory`` é patcheado para usar a sessão do banco de teste.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Pipeline, PipelineRun, User
from app.mcp_server.tools import ToolError
from app.mcp_server.tools.pipelines import (
    create_pipeline,
    delete_pipeline,
    get_pipeline,
    list_pipelines,
    update_pipeline,
    validate_pipeline,
)
from app.mcp_server.tools.runs import (
    cancel_run,
    get_run,
    list_runs,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mcp_env(session: AsyncSession, test_user: User):
    """Prepara o ambiente das tools MCP de pipelines e runs.

    - Patcheia ``get_current_mcp_user`` (módulos das tools) para retornar o
      usuário de teste.
    - Patcheia ``async_session_factory`` (módulos das tools) para usar a
      sessão do banco de teste.

    Retorna o usuário de teste.
    """

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.pipelines.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.pipelines.async_session_factory",
            fake_session_factory,
        ),
        patch(
            "app.mcp_server.tools.runs.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.runs.async_session_factory",
            fake_session_factory,
        ),
    ):
        yield test_user


# ---------------------------------------------------------------------------
# Tests: Pipelines
# ---------------------------------------------------------------------------


class TestCreatePipeline:
    async def test_create_pipeline_minimal(self, mcp_env: User):
        """create_pipeline com args mínimos cria a pipeline e retorna o id."""
        result = await create_pipeline(name="Pipeline de Teste")
        assert result["name"] == "Pipeline de Teste"
        assert result["id"] is not None
        assert result["status"] == "draft"
        assert result["nodes"] == []
        assert result["edges"] == []

    async def test_create_pipeline_with_description(self, mcp_env: User):
        """create_pipeline com description persiste o valor."""
        result = await create_pipeline(
            name="Pipeline Desc", description="Minha descrição"
        )
        assert result["description"] == "Minha descrição"

    async def test_create_pipeline_with_nodes_and_edges(self, mcp_env: User):
        """create_pipeline com nodes e edges persiste o grafo."""
        agent_id = str(uuid.uuid4())
        node_id = str(uuid.uuid4())
        result = await create_pipeline(
            name="Pipeline Grafo",
            nodes=[
                {
                    "id": node_id,
                    "agentId": agent_id,
                    "agentSnapshot": {"agentId": agent_id, "name": "Agente"},
                }
            ],
            edges=[],
        )
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["agentId"] == agent_id
        assert result["edges"] == []

    async def test_create_pipeline_rejects_orphan_nodes(self, mcp_env: User):
        """create_pipeline com nós sem edges de entrada é rejeitada (regra 8).

        Cenário real: client MCP criou 10 nós e 0 edges -> 9 nós órfãos.
        """
        agent_id = str(uuid.uuid4())
        nodes = [
            {"id": str(uuid.uuid4()), "agentId": agent_id,
             "agentSnapshot": {"agentId": agent_id, "name": f"Agente {i}"}}
            for i in range(3)
        ]
        with pytest.raises(ToolError) as exc_info:
            await create_pipeline(name="Pipeline Órfãos", nodes=nodes, edges=[])
        assert "Grafo inválido" in exc_info.value.message
        assert "regra 8" in exc_info.value.message

    async def test_create_pipeline_accepts_connected_graph(self, mcp_env: User):
        """create_pipeline com grafo conectado (entry -> B -> C) é aceita."""
        agent_id = str(uuid.uuid4())
        a, b, c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        result = await create_pipeline(
            name="Pipeline Conectada",
            entry_node_id=a,
            nodes=[
                {"id": a, "agentId": agent_id,
                 "agentSnapshot": {"agentId": agent_id, "name": "A"}},
                {"id": b, "agentId": agent_id,
                 "agentSnapshot": {"agentId": agent_id, "name": "B"}},
                {"id": c, "agentId": agent_id,
                 "agentSnapshot": {"agentId": agent_id, "name": "C"}},
            ],
            edges=[
                {"id": str(uuid.uuid4()), "type": "flow", "source": a, "target": b},
                {"id": str(uuid.uuid4()), "type": "flow", "source": b, "target": c},
            ],
        )
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2


class TestListPipelines:
    async def test_list_pipelines_empty(self, mcp_env: User):
        """list_pipelines sem pipelines retorna lista vazia."""
        result = await list_pipelines()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 20

    async def test_list_pipelines_with_items(self, mcp_env: User):
        """list_pipelines retorna as pipelines criadas."""
        await create_pipeline(name="Pipeline 1")
        await create_pipeline(name="Pipeline 2")
        result = await list_pipelines()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_pipelines_filter_by_status(self, mcp_env: User):
        """list_pipelines com status filtra por status."""
        await create_pipeline(name="Pipeline Draft")
        result = await list_pipelines(status="draft")
        assert result["total"] == 1
        assert result["items"][0]["status"] == "draft"


class TestGetPipeline:
    async def test_get_pipeline_success(self, mcp_env: User):
        """get_pipeline com id válido retorna a pipeline."""
        created = await create_pipeline(name="Encontrar-me")
        result = await get_pipeline(created["id"])
        assert result["id"] == created["id"]
        assert result["name"] == "Encontrar-me"

    async def test_get_pipeline_not_found(self, mcp_env: User):
        """get_pipeline com id inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await get_pipeline(str(uuid.uuid4()))

    async def test_get_pipeline_invalid_id(self, mcp_env: User):
        """get_pipeline com id inválido (não-UUID) lança ToolError."""
        with pytest.raises(ToolError) as exc_info:
            await get_pipeline("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestUpdatePipeline:
    async def test_update_pipeline_name(self, mcp_env: User):
        """update_pipeline com name altera o nome."""
        created = await create_pipeline(name="Original")
        result = await update_pipeline(created["id"], name="Atualizado")
        assert result["name"] == "Atualizado"

    async def test_update_pipeline_description(self, mcp_env: User):
        """update_pipeline com description altera a descrição."""
        created = await create_pipeline(name="Desc Teste")
        result = await update_pipeline(
            created["id"], description="Nova descrição"
        )
        assert result["description"] == "Nova descrição"

    async def test_update_pipeline_not_found(self, mcp_env: User):
        """update_pipeline com id inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await update_pipeline(str(uuid.uuid4()), name="X")

    async def test_update_pipeline_no_fields(self, mcp_env: User):
        """update_pipeline sem nenhum campo lança ToolError."""
        created = await create_pipeline(name="Sem-update")
        with pytest.raises(ToolError) as exc_info:
            await update_pipeline(created["id"])
        assert "Nenhum campo" in exc_info.value.message

    async def test_update_pipeline_rejects_orphan_nodes(self, mcp_env: User):
        """update_pipeline com grafo de nós órfãos é rejeitada (regra 8)."""
        created = await create_pipeline(name="Base")
        agent_id = str(uuid.uuid4())
        nodes = [
            {"id": str(uuid.uuid4()), "agentId": agent_id,
             "agentSnapshot": {"agentId": agent_id, "name": f"Agente {i}"}}
            for i in range(2)
        ]
        with pytest.raises(ToolError) as exc_info:
            await update_pipeline(created["id"], nodes=nodes, edges=[])
        assert "Grafo inválido" in exc_info.value.message


class TestDeletePipeline:
    async def test_delete_pipeline_success(self, mcp_env: User):
        """delete_pipeline remove a pipeline."""
        created = await create_pipeline(name="Remover-me")
        result = await delete_pipeline(created["id"])
        assert result["success"] is True
        # Verifica que não existe mais.
        with pytest.raises(ToolError):
            await get_pipeline(created["id"])

    async def test_delete_pipeline_not_found(self, mcp_env: User):
        """delete_pipeline com id inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await delete_pipeline(str(uuid.uuid4()))


class TestValidatePipeline:
    async def test_validate_pipeline_valid(self, mcp_env: User):
        """validate_pipeline com grafo válido retorna errors vazia."""
        agent_id = str(uuid.uuid4())
        node_id = str(uuid.uuid4())
        result = await validate_pipeline(
            name="Pipeline Válida",
            entry_node_id=node_id,
            nodes=[
                {
                    "id": node_id,
                    "agentId": agent_id,
                    "agentSnapshot": {
                        "agentId": agent_id,
                        "name": "Agente",
                        "inputs": [],
                        "outputs": [],
                        "actions": ["finalize"],
                    },
                }
            ],
            edges=[],
        )
        assert result["errors"] == []

    async def test_validate_pipeline_invalid_entry(self, mcp_env: User):
        """validate_pipeline com entryNodeId inexistente lança ToolError."""
        agent_id = str(uuid.uuid4())
        node_id = str(uuid.uuid4())
        with pytest.raises(ToolError) as exc_info:
            await validate_pipeline(
                name="Pipeline Inválida",
                entry_node_id=str(uuid.uuid4()),  # UUID que não é um nó
                nodes=[
                    {
                        "id": node_id,
                        "agentId": agent_id,
                        "agentSnapshot": {
                            "agentId": agent_id,
                            "name": "Agente",
                            "inputs": [],
                            "outputs": [],
                            "actions": ["finalize"],
                        },
                    }
                ],
                edges=[],
            )
        assert "validar" in exc_info.value.message


# ---------------------------------------------------------------------------
# Tests: Runs
# ---------------------------------------------------------------------------


class TestListRuns:
    async def test_list_runs_empty(self, mcp_env: User):
        """list_runs sem runs retorna lista vazia."""
        pipeline = await create_pipeline(name="Pipeline Runs")
        result = await list_runs(pipeline["id"])
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 20

    async def test_list_runs_not_found(self, mcp_env: User):
        """list_runs com pipeline inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await list_runs(str(uuid.uuid4()))

    async def test_list_runs_with_items(self, mcp_env: User, session: AsyncSession):
        """list_runs retorna os runs criados."""
        from datetime import UTC, datetime

        pipeline = await create_pipeline(name="Pipeline Com Runs")
        # Cria runs diretamente no banco.
        for i in range(3):
            run = PipelineRun(
                id=uuid.uuid4(),
                owner_id=mcp_env.owner_id,
                pipeline_id=uuid.UUID(pipeline["id"]),
                thread_id=f"{pipeline['id']}:run{i}",
                status="completed",
                started_at=datetime.now(UTC),
            )
            session.add(run)
        await session.commit()

        result = await list_runs(pipeline["id"])
        assert result["total"] == 3
        assert len(result["items"]) == 3


class TestGetRun:
    async def test_get_run_success(self, mcp_env: User, session: AsyncSession):
        """get_run com id válido retorna o run."""
        from datetime import UTC, datetime

        pipeline = await create_pipeline(name="Pipeline Get Run")
        run = PipelineRun(
            id=uuid.uuid4(),
            owner_id=mcp_env.owner_id,
            pipeline_id=uuid.UUID(pipeline["id"]),
            thread_id=f"{pipeline['id']}:r1",
            status="completed",
            started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.commit()

        result = await get_run(str(run.id))
        assert result["id"] == str(run.id)
        assert result["status"] == "completed"
        assert result["pipelineId"] == pipeline["id"]

    async def test_get_run_not_found(self, mcp_env: User):
        """get_run com id inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await get_run(str(uuid.uuid4()))

    async def test_get_run_invalid_id(self, mcp_env: User):
        """get_run com id inválido (não-UUID) lança ToolError."""
        with pytest.raises(ToolError) as exc_info:
            await get_run("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestRunPipelineAuth:
    async def test_run_pipeline_not_authenticated(self, session: AsyncSession):
        """run_pipeline sem usuário no contextvar lança ToolError."""

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.runs.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.runs.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await run_pipeline(str(uuid.uuid4()))
            assert "Não autenticado" in exc_info.value.message


class TestCancelRunAuth:
    async def test_cancel_run_not_authenticated(self, session: AsyncSession):
        """cancel_run sem usuário no contextvar lança ToolError."""

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.runs.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.runs.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await cancel_run(str(uuid.uuid4()))
            assert "Não autenticado" in exc_info.value.message


# ---------------------------------------------------------------------------
# Tests: Autenticação (pipelines)
# ---------------------------------------------------------------------------


class TestPipelinesAuth:
    async def test_create_pipeline_not_authenticated(self, session: AsyncSession):
        """create_pipeline sem usuário no contextvar lança ToolError."""

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.pipelines.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.pipelines.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await create_pipeline(name="Sem auth")
            assert "Não autenticado" in exc_info.value.message

    async def test_list_pipelines_not_authenticated(self, session: AsyncSession):
        """list_pipelines sem usuário no contextvar lança ToolError."""

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.pipelines.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.pipelines.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await list_pipelines()
            assert "Não autenticado" in exc_info.value.message
