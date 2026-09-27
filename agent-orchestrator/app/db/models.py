"""SQLAlchemy 2 models for every persisted interface of spec §4 + D3 §3.1.

Dono: db-models (FASE 2). Fontes de verdade, em ordem de precedência:
CONTRATO-TECNICO.md (ADR-006/009/010, §11), spec §4, D3-data-model.md §3.1,
PLANO-BACKEND.md §2.5.

Convenções (registradas para o nó db-migrations):
- Enums: ``sqlalchemy.Enum(native_enum=False, length=...)`` em TODAS as colunas
  de enum (String + CHECK constraint, não enum nativo do Postgres).
- IDs: UUID v4 gerados no Python (``default=uuid.uuid4``); coluna ``UUID(as_uuid=True)``.
- ``created_at``/``updated_at``: ``server_default=func.now()``; ``updated_at`` com ``onupdate``.
- JSONB sempre JSON-serializável.
- ``owner_id`` (FK -> users.id) em todo recurso com ``ownerId`` na spec; unicidade
  de nome é **por owner** (UniqueConstraint com owner_id), nunca global.
- A coluna ``metadata`` (reservada na Declarative API) é mapeada como atributo
  ``meta`` com nome de coluna ``"metadata"``.
- Tabela de checkpoint da aplicação: ``run_checkpoints`` (evita colisão com as
  tabelas ``checkpoints``/``checkpoint_writes``/``checkpoint_blobs``/
  ``checkpoint_migrations`` criadas pelo ``PostgresSaver.setup()`` do LangGraph).
- O grafo da pipeline tem UMA fonte de verdade: as tabelas ``pipeline_nodes`` e
  ``pipeline_edges`` (spec 4.2 + ADR-006 do contrato). Não há JSONB de grafo no
  ``Pipeline``. ``entry_node_id`` é explícito (ADR-010).
- ``agent_snapshot`` (JSONB em ``pipeline_nodes``) carrega exatamente os campos
  da spec 4.2 (sem ``capabilities``; ADR-008/X-01: derivado em runtime no worker).
- ``knowledge_chunk.embedding``: ``pgvector.Vector(1536)`` (dimensão fixa na V1).
  O índice HNSW (``vector_cosine_ops``) é criado na migration (db-migrations),
  não pelo model.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# ---------------------------------------------------------------------------
# Enumerations (native_enum=False em todas: String + CHECK constraint).
# ---------------------------------------------------------------------------

PipelineStatus = Enum(
    "pipeline_status",
    "draft",
    "running",
    "paused",
    "completed",
    "failed",
    native_enum=False,
    length=16,
)

PipelineRunStatus = Enum(
    "pipeline_run_status",
    "running",
    "paused",
    "completed",
    "failed",
    "cancelled",
    native_enum=False,
    length=19,
)

CheckpointStatus = Enum(
    "checkpoint_status",
    "completed",
    "interrupted",
    "failed",
    native_enum=False,
    length=17,
)

SkillCategory = Enum(
    "skill_category",
    "code",
    "docs",
    "infra",
    "communication",
    "analysis",
    native_enum=False,
    length=16,
)

SkillType = Enum("skill_type", "prompt", native_enum=False, length=16)

CustomToolStatus = Enum(
    "custom_tool_status",
    "draft",
    "deployed",
    "archived",
    native_enum=False,
    length=18,
)

MCPTransport = Enum(
    "mcp_transport",
    "stdio",
    "sse",
    "http",
    native_enum=False,
    length=16,
)

MCPStatus = Enum(
    "mcp_status",
    "connected",
    "disconnected",
    "error",
    native_enum=False,
    length=16,
)

KnowledgeScope = Enum(
    "knowledge_scope",
    "global",
    "agent",
    "pipeline",
    native_enum=False,
    length=16,
)

KnowledgeSource = Enum(
    "knowledge_source",
    "upload",
    "vector-db",
    "url",
    "rivvn",
    native_enum=False,
    length=16,
)

KnowledgeDocSource = Enum(
    "knowledge_doc_source",
    "upload",
    "url",
    native_enum=False,
    length=20,
)

KnowledgeDocStatus = Enum(
    "knowledge_doc_status",
    "processing",
    "ready",
    "failed",
    native_enum=False,
    length=20,
)

RivvnContractStatus = Enum(
    "rivvn_contract_status",
    "active",
    "inactive",
    "expired",
    native_enum=False,
    length=21,
)

RivvnStatus = Enum(
    "rivvn_status",
    "connected",
    "disconnected",
    "expired",
    native_enum=False,
    length=16,
)

IntegrationType = Enum(
    "integration_type",
    "github",
    "azure",
    "gitlab",
    native_enum=False,
    length=16,
)

IntegrationStatus = Enum(
    "integration_status",
    "active",
    "disabled",
    native_enum=False,
    length=18,
)

ArtifactType = Enum(
    "artifact_type",
    "code",
    "document",
    "image",
    "other",
    native_enum=False,
    length=16,
)

ApprovalStatus = Enum(
    "approval_status",
    "pending",
    "approved",
    "rejected",
    "revised",
    "cancelled",
    native_enum=False,
    length=16,
)

NotificationChannel = Enum(
    "notification_channel",
    "in-app",
    "email",
    "teams",
    "slack",
    native_enum=False,
    length=20,
)

EdgeType = Enum("edge_type", "flow", "data", native_enum=False, length=9)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _owner_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# User (contrato §5; seed cria o admin; sub do JWT == owner_id, §11.19)
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    # V1 single-user: o seed grava owner_id = id do próprio admin (sub == owner_id).
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = _created_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"


# ---------------------------------------------------------------------------
# Agent (spec 4.1)
# ---------------------------------------------------------------------------


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_agents_owner_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Tipo livre definido pelo usuário (spec 4.1: não é enum fixo).
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    strategy: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Mochila: refs JSON-serializáveis (SkillRef[], ToolRef[], MCPServerRef[],
    # KnowledgeRef[], IntegrationRef[]).
    skills: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    tools: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    mcp_servers: Mapped[list[Any]] = mapped_column(
        "mcpServers", JSONB, nullable=False, default=list
    )
    knowledge: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    integrations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # Contrato de fluxo: PortDef[] / PortDef[] / FlowAction[].
    inputs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    outputs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    actions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="gpt-4o")
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    shell_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Agent {self.name}>"


# ---------------------------------------------------------------------------
# Pipeline (spec 4.2) — grafo em pipeline_nodes / pipeline_edges (uma fonte de
# verdade; ADR-006 do contrato). entry_node_id explícito (ADR-010).
# ---------------------------------------------------------------------------


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_pipelines_owner_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[PipelineStatus] = mapped_column(PipelineStatus, nullable=False, default="draft")
    # PipelineNode.id do nó de entrada (UUID, ADR-010). Sem FK: o nó pode ser
    # recriado ao editar o grafo; o validador (pe-validator) garante a referência.
    entry_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    current_checkpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    nodes: Mapped[list["PipelineNode"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan", passive_deletes=True
    )
    edges: Mapped[list["PipelineEdge"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan", passive_deletes=True
    )
    runs: Mapped[list["PipelineRun"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pipeline {self.name}>"


class PipelineNode(Base):
    __tablename__ = "pipeline_nodes"
    __table_args__ = (UniqueConstraint("pipeline_id", "id", name="uq_pipeline_nodes_pipeline_id"),)

    # id == nodeId: identificador único do nó no grafo (distingui instâncias do
    # mesmo agente em loops). PK própria; pipeline_id indexado.
    id: Mapped[uuid.UUID] = _uuid_pk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Layout no portal (React Flow); o compiler ignora (D5).
    position: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Cópia imutável do agente no momento da execução. Exatamente os campos da
    # spec 4.2 AgentSnapshot (sem capabilities; ADR-008/X-01).
    agent_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    pipeline: Mapped["Pipeline"] = relationship(back_populates="nodes")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PipelineNode {self.id}>"


class PipelineEdge(Base):
    __tablename__ = "pipeline_edges"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "id", name="uq_pipeline_edges_pipeline_id"),
        # ADR-006 do contrato: rejectTarget configurável na aresta.
        CheckConstraint(
            "type IN ('flow', 'data')",
            name="ck_pipeline_edges_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[EdgeType] = mapped_column(EdgeType, nullable=False)
    # source/target: PipelineNode.id (UUID).
    source: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    target: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # EdgeCondition (structured; apenas em edges de flow).
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_channel: Mapped[Optional[NotificationChannel]] = mapped_column(  # noqa: UP007
        NotificationChannel, nullable=True
    )
    approval_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # DataMapping (obrigatório quando type == "data").
    data_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # ADR-006 do contrato: target de rejeição (nó real ou "END").
    reject_target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    pipeline: Mapped["Pipeline"] = relationship(back_populates="edges")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PipelineEdge {self.type} {self.source} -> {self.target}>"


# ---------------------------------------------------------------------------
# PipelineRun (spec 4.2)
# ---------------------------------------------------------------------------


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (UniqueConstraint("pipeline_id", "thread_id", name="uq_pipeline_runs_thread"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Convenção: f"{pipelineId}:{runId}" (spec 4.2).
    thread_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    status: Mapped[PipelineRunStatus] = mapped_column(
        PipelineRunStatus, nullable=False, default="running"
    )
    current_checkpoint_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="runs")
    checkpoints: Mapped[list["Checkpoint"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PipelineRun {self.thread_id} {self.status}>"


# ---------------------------------------------------------------------------
# Checkpoint (spec 4.3) — tabela da aplicação: run_checkpoints.
# As tabelas `checkpoints`/`checkpoint_writes`/`checkpoint_blobs`/
# `checkpoint_migrations` são do LangGraph PostgresSaver (não são nossas).
# ---------------------------------------------------------------------------


class Checkpoint(Base):
    __tablename__ = "run_checkpoints"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[CheckpointStatus] = mapped_column(
        CheckpointStatus, nullable=False, default="completed"
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Coluna "metadata" (reservada na Declarative API) -> atributo `meta`.
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    run: Mapped["PipelineRun"] = relationship(back_populates="checkpoints")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Checkpoint {self.node_id} {self.status}>"


# ---------------------------------------------------------------------------
# Skill (spec 4.4)
# ---------------------------------------------------------------------------


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_skills_owner_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[SkillCategory] = mapped_column(SkillCategory, nullable=False)
    type: Mapped[SkillType] = mapped_column(SkillType, nullable=False, default="prompt")
    # {template, variables} (spec 4.4).
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    inputs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    outputs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    required_integrations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Skill {self.name}>"


# ---------------------------------------------------------------------------
# CustomTool (spec 6.4)
# ---------------------------------------------------------------------------


class CustomTool(Base):
    __tablename__ = "custom_tools"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_custom_tools_owner_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="custom")
    script: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # {inputs: ToolParam[], outputs: ToolParam[]} (spec 6.4).
    io: Mapped[dict[str, Any]] = mapped_column("io", JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[CustomToolStatus] = mapped_column(
        CustomToolStatus, nullable=False, default="draft"
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CustomTool {self.name} v{self.version}>"


# ---------------------------------------------------------------------------
# MCPServer (spec 6.7)
# ---------------------------------------------------------------------------


class MCPServer(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_mcp_servers_owner_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    transport: Mapped[MCPTransport] = mapped_column(MCPTransport, nullable=False)
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # secrets ref, nunca valor em claro (spec 6.7).
    env: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[MCPStatus] = mapped_column(MCPStatus, nullable=False, default="disconnected")
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # MCPToolInfo[] (name, description, inputSchema).
    discovered_tools: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MCPServer {self.name} {self.transport}>"


# ---------------------------------------------------------------------------
# KnowledgeBase (spec 4.6)
# ---------------------------------------------------------------------------


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_knowledge_bases_owner_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[KnowledgeScope] = mapped_column(KnowledgeScope, nullable=False)
    # agentId ou pipelineId (quando scope != "global").
    scope_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[KnowledgeSource] = mapped_column(KnowledgeSource, nullable=False)
    reference: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=512)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=64)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    embedding_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="text-embedding-3-small"
    )
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False, default=1536)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan", passive_deletes=True
    )
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeBase {self.name} {self.source}>"


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[KnowledgeDocSource] = mapped_column(KnowledgeDocSource, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[KnowledgeDocStatus] = mapped_column(
        KnowledgeDocStatus, nullable=False, default="processing"
    )
    created_at: Mapped[datetime] = _created_at()

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeDocument {self.name} {self.status}>"


# ---------------------------------------------------------------------------
# KnowledgeChunk (pgvector; D3 §3.1). embedding vector(1536) fixo na V1.
# Índice HNSW (vector_cosine_ops) criado na migration (db-migrations).
# ---------------------------------------------------------------------------


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding: Mapped[Any] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="chunks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeChunk kb={self.knowledge_base_id} #{self.chunk_index}>"


# ---------------------------------------------------------------------------
# ApprovalRequest (spec 4.5; ADR-009 do contrato).
# Chave de idempotência do upsert: (pipeline_id, node_id, checkpoint_id).
# ---------------------------------------------------------------------------


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_id",
            "node_id",
            "checkpoint_id",
            name="uq_approval_requests_pipeline_node_checkpoint",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    node_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # interruptId/checkpoint do LangGraph (PLANO-BACKEND F6).
    checkpoint_id: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    artifacts: Mapped[list[Any] | None] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        ApprovalStatus, nullable=False, default="pending"
    )
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        NotificationChannel, nullable=False, default="in-app"
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    attempted_channels: Mapped[list[Any]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    fallback_channel: Mapped[Optional[NotificationChannel]] = mapped_column(  # noqa: UP007
        NotificationChannel, nullable=True
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ApprovalRequest {self.status} node={self.node_id}>"


# ---------------------------------------------------------------------------
# Artifact (spec 4.5)
# ---------------------------------------------------------------------------


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    type: Mapped[ArtifactType] = mapped_column(ArtifactType, nullable=False)
    # V1: texto no Postgres (limite 10MB). V2: S3.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()

    run: Mapped["PipelineRun"] = relationship(back_populates="artifacts")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Artifact {self.name} {self.type}>"


# ---------------------------------------------------------------------------
# Integration (spec 4.7)
# ---------------------------------------------------------------------------


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_integrations_owner_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    type: Mapped[IntegrationType] = mapped_column(IntegrationType, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[IntegrationStatus] = mapped_column(
        IntegrationStatus, nullable=False, default="active"
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Integration {self.type} {self.name}>"


# ---------------------------------------------------------------------------
# RivvnConnection (spec 7.4; gate comercial; fora do caminho crítico da V1)
# ---------------------------------------------------------------------------


class RivvnConnection(Base):
    __tablename__ = "rivvn_connections"
    __table_args__ = (UniqueConstraint("owner_id", name="uq_rivvn_connections_owner"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _owner_fk()
    contract_status: Mapped[RivvnContractStatus] = mapped_column(
        RivvnContractStatus, nullable=False, default="inactive"
    )
    status: Mapped[RivvnStatus] = mapped_column(RivvnStatus, nullable=False, default="disconnected")
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[list[Any]] = mapped_column(ARRAY(String), nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RivvnConnection {self.contract_status} {self.status}>"
