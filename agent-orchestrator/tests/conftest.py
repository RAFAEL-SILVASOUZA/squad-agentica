"""Fixtures de banco de teste isolado (contrato §4 / protocolo comum §5).

Cada sessão de pytest cria um banco próprio ``agent_portal_test_<uuid>`` e o
destrói no teardown. O fixture usa o mesmo ``DATABASE_URL`` base mudando apenas
o nome do banco; o usuário ``agent_portal`` tem ``CREATEDB`` (postgres/init.sql).
Nunca usa o banco ``agent_portal``.
"""

from __future__ import annotations

import re
import subprocess
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.session import Base


def _test_database_url() -> str:
    """DATABASE_URL do banco de teste isolado (mesmo host/credenciais, banco novo)."""
    parsed = urlparse(settings.database_url)
    db_name = f"agent_portal_test_{uuid.uuid4().hex[:12]}"
    return urlunparse(parsed._replace(path=f"/{db_name}"))


def _asyncpg_url(url: str) -> str:
    """Converte ``postgresql+asyncpg://`` em ``postgresql://`` para o driver asyncpg."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _test_database_url()


@pytest_asyncio.fixture(scope="function")
async def test_engine(test_database_url: str):
    """Cria o banco de teste, o schema (create_all) e o engine async.

    Teardown: drop do schema, drop do banco, dispose do engine.
    """
    # Cria o banco (fora de transação: CREATE DATABASE não transaciona).
    # Conecta no banco de aplicação (que existe) para criar o banco de teste.
    admin_url = _asyncpg_url(settings.database_url)
    db_match = re.search(r"/(agent_portal_test_[a-f0-9]+)$", test_database_url)
    db_name = db_match.group(1) if db_match else "agent_portal_test_unknown"
    conn = await asyncpg.connect(admin_url)
    await conn.execute(f'CREATE DATABASE "{db_name}"')
    await conn.close()

    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    # A extensão vector vem do postgres/init.sql (infra-postgres); o banco de
    # teste é criado do zero, então habilitamos aqui (idempotente).
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    conn = await asyncpg.connect(_asyncpg_url(admin_url))
    await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    await conn.close()


@pytest_asyncio.fixture
async def session(test_engine) -> AsyncIterator[AsyncSession]:
    """Sessão por teste (commit no fim, rollback em falha)."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# Import shared API fixtures so pytest can discover them from integration_api_fixtures
from tests.integration_api_fixtures import (  # noqa: F401
    client,
    full_app,
    full_client,
    mock_agent_storage,
    owner_id,
    test_app,
    test_user,
)


@pytest_asyncio.fixture
async def make_agent(full_client):  # noqa: F811 (nome do parâmetro == nome do fixture, por design)
    """Cria um agente mínimo via POST /api/agents (usa o ``full_client``: agents+
    integrations+pipelines no mesmo app, de ``tests/integration_api_fixtures.py``)."""

    async def _make(name: str, **overrides):
        body = {
            "name": name,
            "type": "custom",
            "prompt": "Responda com o campo result.",
            "actions": ["finalize"],
            **overrides,
        }
        resp = await full_client.post("/api/agents", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


@pytest_asyncio.fixture
async def make_git_integration(full_client):  # noqa: F811 (nome do parâmetro == nome do fixture, por design)
    """Cria uma integração git (github por padrão) via POST /api/integrations."""

    async def _make(type: str = "github", **overrides):
        body = {
            "type": type,
            "name": f"git-{uuid.uuid4().hex[:8]}",
            "config": {"organization": "org"} if type == "azure" else {},
            **overrides,
        }
        resp = await full_client.post("/api/integrations", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


@pytest_asyncio.fixture
async def other_user(session: AsyncSession):
    """Segundo usuário autenticado, para os testes de isolamento (F4)."""
    from app.db.models import User as _User

    user = _User(
        id=uuid.uuid4(), email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        name="Other User", password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def client_other_user(full_app, other_user):  # noqa: F811 (nome do parâmetro == nome do fixture, por design)
    """``full_client`` autenticado como um usuário diferente (isolamento)."""
    from httpx import ASGITransport, AsyncClient

    from app.auth.dependencies import get_current_user

    async def override_get_current_user():
        return other_user

    full_app.dependency_overrides[get_current_user] = override_get_current_user
    transport = ASGITransport(app=full_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def make_run_with_workspace(session, test_user, tmp_path, monkeypatch):  # noqa: F811 (nome do parâmetro == nome do fixture, por design)
    """Cria uma pipeline + run (status ``completed``) do usuário de teste e um
    workspace vazio (``WorkspaceManager.create_empty``) sob ``tmp_path``,
    monkeypatchando ``WorkspaceManager`` em ``app.api.workspaces`` para usar
    essa raiz isolada. Retorna ``(run_id, workspace_path)``."""
    from datetime import UTC, datetime

    import app.api.workspaces as workspaces_module
    from app.db.models import Pipeline, PipelineRun
    from app.runtime.workspace import WorkspaceManager

    ws_root = tmp_path / "workspaces"
    monkeypatch.setattr(workspaces_module, "WorkspaceManager", lambda: WorkspaceManager(ws_root))

    async def _make(name: str = "Projeto de teste"):
        pipeline = Pipeline(
            id=uuid.uuid4(), owner_id=test_user.owner_id, name=name, description="",
            status="completed", entry_node_id=uuid.uuid4(),
        )
        session.add(pipeline)
        await session.flush()
        run = PipelineRun(
            id=uuid.uuid4(), owner_id=test_user.owner_id, pipeline_id=pipeline.id,
            thread_id=f"{pipeline.id}:r", status="completed", started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.commit()
        wm = WorkspaceManager(ws_root)
        path = wm.create_empty(str(run.id))
        return str(run.id), path

    return _make


@pytest_asyncio.fixture
async def make_run_with_git_workspace(session, test_user, tmp_path, monkeypatch, remote):  # noqa: F811 (nome do parâmetro == nome do fixture, por design)
    """Como ``make_run_with_workspace``, mas o workspace é um clone real do
    fixture ``remote`` (repositório bare local) — para testes que precisam de
    um diff de verdade (ex.: truncamento e arquivo binário em
    ``GET /api/runs/:runId/diff``, Task 8 fix round 1)."""
    from datetime import UTC, datetime

    import app.api.workspaces as workspaces_module
    from app.db.models import Pipeline, PipelineRun
    from app.runtime.workspace import WorkspaceManager

    ws_root = tmp_path / "workspaces"
    monkeypatch.setattr(workspaces_module, "WorkspaceManager", lambda: WorkspaceManager(ws_root))

    async def _make(name: str = "Projeto de teste"):
        pipeline = Pipeline(
            id=uuid.uuid4(), owner_id=test_user.owner_id, name=name, description="",
            status="completed", entry_node_id=uuid.uuid4(),
        )
        session.add(pipeline)
        await session.flush()
        run = PipelineRun(
            id=uuid.uuid4(), owner_id=test_user.owner_id, pipeline_id=pipeline.id,
            thread_id=f"{pipeline.id}:r", status="completed", started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.commit()
        wm = WorkspaceManager(ws_root)
        path = await wm.clone(str(run.id), remote, "main")
        return str(run.id), path

    return _make


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path) -> str:
    """Repositório bare local usado como "remote" nos testes de workspace/git.

    Compartilhado com a Task 7 (publicação de PR), que reusa este fixture.
    """
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(bare), str(seed))
    (seed / "README.md").write_text("# base\n")
    _git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "base")
    _git(seed, "push", "origin", "main")
    return str(bare)
