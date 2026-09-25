"""Testes dos models (db-models, FASE 2).

Cobrem o PLANO-BACKEND Â§2.5 (critÃ©rios de aceite) + CRUD bÃ¡sico por entidade:
(a) importar todos os models;
(b) create_all em banco de teste gera todas as tabelas;
(c) knowledge_chunk.embedding tem tipo vector(1536) (reflection);
(d) User com hash bcrypt vÃ¡lido passa em verify_password;
(e) CRUD bÃ¡sico por entidade (insert/read/update/delete).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db import models as m
from app.db.session import Base

# (a) Importar todos os models sem erro.
ALL_MODELS = [
    m.User,
    m.Agent,
    m.Pipeline,
    m.PipelineNode,
    m.PipelineEdge,
    m.PipelineRun,
    m.Checkpoint,
    m.Skill,
    m.CustomTool,
    m.MCPServer,
    m.KnowledgeBase,
    m.KnowledgeDocument,
    m.KnowledgeChunk,
    m.ApprovalRequest,
    m.Artifact,
    m.Integration,
    m.RivvnConnection,
]

EXPECTED_TABLES = {
    "users",
    "agents",
    "pipelines",
    "pipeline_nodes",
    "pipeline_edges",
    "pipeline_runs",
    "run_checkpoints",
    "skills",
    "custom_tools",
    "mcp_servers",
    "knowledge_bases",
    "knowledge_documents",
    "knowledge_chunks",
    "approval_requests",
    "artifacts",
    "integrations",
    "rivvn_connections",
}


def test_all_models_import() -> None:
    for model in ALL_MODELS:
        assert model.__tablename__ in Base.metadata.tables


def test_expected_tables_registered() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


async def test_create_all_creates_all_tables(test_engine) -> None:
    async with test_engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert EXPECTED_TABLES <= set(tables)


async def test_knowledge_chunk_embedding_is_vector_1536(test_engine) -> None:
    async with test_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("knowledge_chunks")
        )
    embedding = next(c for c in columns if c["name"] == "embedding")
    assert "VECTOR" in str(embedding["type"]).upper()
    assert "1536" in str(embedding["type"])


async def test_user_bcrypt_roundtrip() -> None:
    password = "senha-forte-123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("senha-errada", hashed)


# ---------------------------------------------------------------------------
# CRUD bÃ¡sico por entidade
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession, email: str = "owner@example.com") -> m.User:
    uid = uuid.uuid4()
    # V1 single-user: owner_id = id do prÃ³prio admin (sub == owner_id, Â§11.19).
    user = m.User(
        id=uid,
        email=email,
        name="Owner",
        password_hash=hash_password("owner-pass-123"),
        owner_id=uid,
    )
    session.add(user)
    await session.commit()
    return user


async def test_user_crud(session: AsyncSession) -> None:
    user = await _make_user(session)
    got = (await session.execute(select(m.User).where(m.User.id == user.id))).scalar_one()
    assert got.email == "owner@example.com"
    assert verify_password("owner-pass-123", got.password_hash)
    got.name = "Owner Renamed"
    await session.commit()
    got = (await session.execute(select(m.User).where(m.User.id == user.id))).scalar_one()
    assert got.name == "Owner Renamed"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.User).where(m.User.id == user.id))
    ).scalar_one_or_none() is None


async def test_agent_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    agent = m.Agent(
        owner_id=owner.id,
        name="planner",
        type="planner",
        description="Planeja",
        prompt="Seja um planner",
        strategy="1. Leia 2. Planeje",
        skills=[{"skillId": "s1", "config": {}}],
        tools=[],
        mcp_servers=[],
        knowledge=[],
        integrations=[],
        inputs=[{"name": "brief", "type": "document", "required": True}],
        outputs=[{"name": "plano", "type": "document", "required": False}],
        actions=["follow", "finalize"],
        model="gpt-4o",
        max_iterations=5,
        timeout=120,
        shell_access=False,
    )
    session.add(agent)
    await session.commit()

    got = (await session.execute(select(m.Agent).where(m.Agent.id == agent.id))).scalar_one()
    assert got.name == "planner"
    assert got.inputs[0]["name"] == "brief"
    got.name = "planner-v2"
    got.max_iterations = 7
    await session.commit()
    got = (await session.execute(select(m.Agent).where(m.Agent.id == agent.id))).scalar_one()
    assert got.name == "planner-v2"
    assert got.max_iterations == 7
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.Agent).where(m.Agent.id == agent.id))
    ).scalar_one_or_none() is None


async def test_pipeline_graph_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    agent = m.Agent(owner_id=owner.id, name="dev", type="developer")
    session.add(agent)
    await session.flush()

    pipeline_id = uuid.uuid4()
    node_a_id = uuid.uuid4()
    pipeline = m.Pipeline(
        id=pipeline_id,
        owner_id=owner.id,
        name="pipeline-a",
        description="Grafo de teste",
        entry_node_id=node_a_id,
    )
    node_a = m.PipelineNode(
        id=node_a_id,
        pipeline_id=pipeline_id,
        agent_id=agent.id,
        position={"x": 0, "y": 0},
        label="A",
        agent_snapshot={
            "agentId": str(agent.id),
            "version": 1,
            "name": "dev",
            "description": "",
            "prompt": "p",
            "strategy": "s",
            "skills": [],
            "tools": [],
            "mcpServers": [],
            "knowledge": [],
            "integrations": [],
            "inputs": [],
            "outputs": [],
            "actions": ["follow"],
            "model": "gpt-4o",
            "maxIterations": 3,
            "timeout": 60,
            "shellAccess": False,
        },
    )
    node_b_id = uuid.uuid4()
    node_b = m.PipelineNode(
        id=node_b_id,
        pipeline_id=pipeline_id,
        agent_id=agent.id,
        position={"x": 200, "y": 0},
        agent_snapshot={"agentId": str(agent.id), "version": 1, "name": "dev"},
    )
    edge_flow = m.PipelineEdge(
        pipeline_id=pipeline_id,
        type="flow",
        source=node_a_id,
        target=node_b_id,
        requires_approval=False,
    )
    edge_data = m.PipelineEdge(
        pipeline_id=pipeline_id,
        type="data",
        source=node_a_id,
        target=node_b_id,
        data_mapping={"sourceOutput": "code", "targetInput": "code"},
    )
    session.add_all([pipeline, node_a, node_b, edge_flow, edge_data])
    await session.commit()

    got = (
        await session.execute(select(m.Pipeline).where(m.Pipeline.id == pipeline.id))
    ).scalar_one()
    assert got.entry_node_id == node_a.id
    assert got.status == "draft"
    nodes = (
        (
            await session.execute(
                select(m.PipelineNode).where(m.PipelineNode.pipeline_id == pipeline.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(nodes) == 2
    edges = (
        (
            await session.execute(
                select(m.PipelineEdge).where(m.PipelineEdge.pipeline_id == pipeline.id)
            )
        )
        .scalars()
        .all()
    )
    assert {e.type for e in edges} == {"flow", "data"}
    data_edge = next(e for e in edges if e.type == "data")
    assert data_edge.data_mapping["sourceOutput"] == "code"

    got.status = "running"
    await session.commit()
    got = (
        await session.execute(select(m.Pipeline).where(m.Pipeline.id == pipeline.id))
    ).scalar_one()
    assert got.status == "running"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.Pipeline).where(m.Pipeline.id == pipeline.id))
    ).scalar_one_or_none() is None


async def test_pipeline_run_and_checkpoint_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    pipeline = m.Pipeline(owner_id=owner.id, name="p-run", entry_node_id=uuid.uuid4())
    session.add(pipeline)
    await session.flush()

    run = m.PipelineRun(
        owner_id=owner.id,
        pipeline_id=pipeline.id,
        thread_id=f"{pipeline.id}:{uuid.uuid4()}",
        status="running",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()

    checkpoint = m.Checkpoint(
        owner_id=owner.id,
        pipeline_id=pipeline.id,
        run_id=run.id,
        node_id="node-1",
        state={"data": {}, "actions": {}},
        status="completed",
        timestamp=datetime.now(UTC),
        meta={"step": 1},
    )
    session.add(checkpoint)
    await session.commit()

    got = (
        await session.execute(select(m.PipelineRun).where(m.PipelineRun.id == run.id))
    ).scalar_one()
    assert got.status == "running"
    cp = (
        await session.execute(select(m.Checkpoint).where(m.Checkpoint.id == checkpoint.id))
    ).scalar_one()
    assert cp.meta["step"] == 1

    got.status = "completed"
    got.completed_at = datetime.now(UTC)
    await session.commit()
    got = (
        await session.execute(select(m.PipelineRun).where(m.PipelineRun.id == run.id))
    ).scalar_one()
    assert got.status == "completed"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.PipelineRun).where(m.PipelineRun.id == run.id))
    ).scalar_one_or_none() is None


async def test_skill_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    skill = m.Skill(
        owner_id=owner.id,
        name="code-gen",
        description="Gera cÃ³digo",
        category="code",
        type="prompt",
        definition={"template": "Gere {{lang}}", "variables": ["lang"]},
        inputs=[{"name": "lang", "type": "string", "required": True}],
        outputs=[{"name": "code", "type": "code", "required": False}],
        required_integrations=[],
    )
    session.add(skill)
    await session.commit()
    got = (await session.execute(select(m.Skill).where(m.Skill.id == skill.id))).scalar_one()
    assert got.definition["variables"] == ["lang"]
    got.description = "Gera cÃ³digo v2"
    await session.commit()
    got = (await session.execute(select(m.Skill).where(m.Skill.id == skill.id))).scalar_one()
    assert got.description == "Gera cÃ³digo v2"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.Skill).where(m.Skill.id == skill.id))
    ).scalar_one_or_none() is None


async def test_custom_tool_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    tool = m.CustomTool(
        owner_id=owner.id,
        name="consultar_jira",
        description="Busca issues",
        category="data",
        script="def execute():\n    return {}",
        io={
            "inputs": [
                {"name": "project_key", "type": "string", "description": "Chave", "required": True}
            ],
            "outputs": [
                {"name": "issues", "type": "array", "description": "Issues", "required": False}
            ],
        },
        version=1,
        status="draft",
    )
    session.add(tool)
    await session.commit()
    got = (
        await session.execute(select(m.CustomTool).where(m.CustomTool.id == tool.id))
    ).scalar_one()
    assert got.io["inputs"][0]["name"] == "project_key"
    got.status = "deployed"
    got.version = 2
    await session.commit()
    got = (
        await session.execute(select(m.CustomTool).where(m.CustomTool.id == tool.id))
    ).scalar_one()
    assert got.status == "deployed"
    assert got.version == 2
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.CustomTool).where(m.CustomTool.id == tool.id))
    ).scalar_one_or_none() is None


async def test_mcp_server_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    server = m.MCPServer(
        owner_id=owner.id,
        name="jira-mcp",
        description="MCP do Jira",
        transport="stdio",
        command="npx -y @acme/mcp-jira",
        env={"JIRA_TOKEN": "secret-ref"},
        status="disconnected",
        discovered_tools=[],
    )
    session.add(server)
    await session.commit()
    got = (
        await session.execute(select(m.MCPServer).where(m.MCPServer.id == server.id))
    ).scalar_one()
    assert got.transport == "stdio"
    got.status = "connected"
    got.discovered_tools = [{"name": "search", "description": "d", "inputSchema": {}}]
    got.last_connected_at = datetime.now(UTC)
    await session.commit()
    got = (
        await session.execute(select(m.MCPServer).where(m.MCPServer.id == server.id))
    ).scalar_one()
    assert got.status == "connected"
    assert got.discovered_tools[0]["name"] == "search"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.MCPServer).where(m.MCPServer.id == server.id))
    ).scalar_one_or_none() is None


async def test_knowledge_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    kb = m.KnowledgeBase(
        owner_id=owner.id,
        name="docs",
        description="DocumentaÃ§Ã£o",
        scope="global",
        source="upload",
        reference="docs",
        chunk_size=512,
        chunk_overlap=64,
        top_k=5,
        similarity_threshold=0.7,
        embedding_model="text-embedding-3-small",
        embedding_dim=1536,
        document_count=0,
    )
    session.add(kb)
    await session.flush()

    doc = m.KnowledgeDocument(
        owner_id=owner.id,
        knowledge_base_id=kb.id,
        name="manual.pdf",
        source="upload",
        size=1024,
        chunk_count=0,
        status="processing",
    )
    session.add(doc)
    await session.flush()

    chunk = m.KnowledgeChunk(
        owner_id=owner.id,
        knowledge_base_id=kb.id,
        document_id=doc.id,
        chunk_index=0,
        content="primeiro chunk",
        embedding=[0.0] * 1536,
    )
    session.add(chunk)
    await session.commit()

    got = (
        await session.execute(select(m.KnowledgeBase).where(m.KnowledgeBase.id == kb.id))
    ).scalar_one()
    assert got.source == "upload"
    assert got.embedding_dim == 1536
    got_doc = (
        await session.execute(select(m.KnowledgeDocument).where(m.KnowledgeDocument.id == doc.id))
    ).scalar_one()
    got_doc.status = "ready"
    got_doc.chunk_count = 1
    got.document_count = 1
    await session.commit()
    got_doc = (
        await session.execute(select(m.KnowledgeDocument).where(m.KnowledgeDocument.id == doc.id))
    ).scalar_one()
    assert got_doc.status == "ready"
    got = (
        await session.execute(select(m.KnowledgeBase).where(m.KnowledgeBase.id == kb.id))
    ).scalar_one()
    assert got.document_count == 1
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.KnowledgeBase).where(m.KnowledgeBase.id == kb.id))
    ).scalar_one_or_none() is None


async def test_approval_request_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    approval = m.ApprovalRequest(
        owner_id=owner.id,
        pipeline_id=uuid.uuid4(),
        node_id="node-1",
        checkpoint_id="interrupt-1",
        message="Aprovar deploy?",
        context={"produced": "code"},
        artifacts=["artifact-1"],
        status="pending",
        channel="in-app",
        sent_at=datetime.now(UTC),
        retry_count=0,
        max_retries=3,
        attempted_channels=["in-app"],
        fallback_channel=None,
        timeout_seconds=3600,
    )
    session.add(approval)
    await session.commit()

    got = (
        await session.execute(select(m.ApprovalRequest).where(m.ApprovalRequest.id == approval.id))
    ).scalar_one()
    assert got.status == "pending"
    assert got.artifacts == ["artifact-1"]
    got.status = "approved"
    got.response = "ok"
    got.responded_by = "admin"
    got.responded_at = datetime.now(UTC)
    await session.commit()
    got = (
        await session.execute(select(m.ApprovalRequest).where(m.ApprovalRequest.id == approval.id))
    ).scalar_one()
    assert got.status == "approved"
    assert got.responded_by == "admin"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.ApprovalRequest).where(m.ApprovalRequest.id == approval.id))
    ).scalar_one_or_none() is None


async def test_artifact_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    pipeline = m.Pipeline(owner_id=owner.id, name="p-art", entry_node_id=uuid.uuid4())
    session.add(pipeline)
    await session.flush()
    run = m.PipelineRun(
        owner_id=owner.id,
        pipeline_id=pipeline.id,
        thread_id=f"{pipeline.id}:{uuid.uuid4()}",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()

    artifact = m.Artifact(
        owner_id=owner.id,
        run_id=run.id,
        node_id="node-1",
        name="report.md",
        type="document",
        content="# RelatÃ³rio",
        size=13,
    )
    session.add(artifact)
    await session.commit()

    got = (
        await session.execute(select(m.Artifact).where(m.Artifact.id == artifact.id))
    ).scalar_one()
    assert got.type == "document"
    got.content = "# RelatÃ³rio v2"
    got.size = 15
    await session.commit()
    got = (
        await session.execute(select(m.Artifact).where(m.Artifact.id == artifact.id))
    ).scalar_one()
    assert got.content == "# RelatÃ³rio v2"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.Artifact).where(m.Artifact.id == artifact.id))
    ).scalar_one_or_none() is None


async def test_integration_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    integration = m.Integration(
        owner_id=owner.id,
        type="github",
        name="github-main",
        config={"owner": "acme", "repos": ["portal"]},
        status="active",
    )
    session.add(integration)
    await session.commit()
    got = (
        await session.execute(select(m.Integration).where(m.Integration.id == integration.id))
    ).scalar_one()
    assert got.config["owner"] == "acme"
    got.status = "disabled"
    await session.commit()
    got = (
        await session.execute(select(m.Integration).where(m.Integration.id == integration.id))
    ).scalar_one()
    assert got.status == "disabled"
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.Integration).where(m.Integration.id == integration.id))
    ).scalar_one_or_none() is None


async def test_rivvn_connection_crud(session: AsyncSession) -> None:
    owner = await _make_user(session)
    rivvn = m.RivvnConnection(
        owner_id=owner.id,
        contract_status="inactive",
        status="disconnected",
        scope=[],
    )
    session.add(rivvn)
    await session.commit()
    got = (
        await session.execute(select(m.RivvnConnection).where(m.RivvnConnection.id == rivvn.id))
    ).scalar_one()
    assert got.contract_status == "inactive"
    got.contract_status = "active"
    got.status = "connected"
    got.connected_at = datetime.now(UTC)
    got.scope = ["read:knowledge"]
    await session.commit()
    got = (
        await session.execute(select(m.RivvnConnection).where(m.RivvnConnection.id == rivvn.id))
    ).scalar_one()
    assert got.contract_status == "active"
    assert got.scope == ["read:knowledge"]
    await session.delete(got)
    await session.commit()
    assert (
        await session.execute(select(m.RivvnConnection).where(m.RivvnConnection.id == rivvn.id))
    ).scalar_one_or_none() is None


async def test_owner_scoped_name_uniqueness(session: AsyncSession) -> None:
    """Unicidade de nome Ã© por owner, nunca global (regra do schema)."""
    owner_a = await _make_user(session, email="a@example.com")
    owner_b = await _make_user(session, email="b@example.com")
    session.add_all(
        [
            m.Agent(owner_id=owner_a.id, name="planner", type="planner"),
            m.Agent(owner_id=owner_b.id, name="planner", type="planner"),
        ]
    )
    await session.commit()
    count = (
        (await session.execute(select(m.Agent).where(m.Agent.name == "planner"))).scalars().all()
    )
    assert len(count) == 2
