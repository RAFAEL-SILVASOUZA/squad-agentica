# Handoff: FASE 2 - DB (db-review aprovado)

Data: 2026-09-25
Veredito: APROVADO (todos os 6 critérios bloqueantes passaram)

## Inventário do que existe

### Models (agent-orchestrator/app/db/models.py)

17 models SQLAlchemy 2 (async, DeclarativeBase):

| Model | Tabela | PK | owner_id | Unicidade de nome |
|-------|--------|----|----------|-------------------|
| User | users | UUID | self-ref (owner_id=id) | email (global) |
| Agent | agents | UUID | FK users.id | (owner_id, name) |
| Pipeline | pipelines | UUID | FK users.id | (owner_id, name) |
| PipelineNode | pipeline_nodes | UUID | - | (pipeline_id, id) |
| PipelineEdge | pipeline_edges | UUID | - | (pipeline_id, id) |
| PipelineRun | pipeline_runs | UUID | FK users.id | (pipeline_id, thread_id) |
| Checkpoint | run_checkpoints | UUID | FK users.id | - |
| Skill | skills | UUID | FK users.id | (owner_id, name) |
| CustomTool | custom_tools | UUID | FK users.id | (owner_id, name) |
| MCPServer | mcp_servers | UUID | FK users.id | (owner_id, name) |
| KnowledgeBase | knowledge_bases | UUID | FK users.id | (owner_id, name) |
| KnowledgeDocument | knowledge_documents | UUID | FK users.id | - |
| KnowledgeChunk | knowledge_chunks | UUID | FK users.id | - |
| ApprovalRequest | approval_requests | UUID | FK users.id | (pipeline_id, node_id, checkpoint_id) |
| Artifact | artifacts | UUID | FK users.id | - |
| Integration | integrations | UUID | FK users.id | (owner_id, name) |
| RivvnConnection | rivvn_connections | UUID | FK users.id | (owner_id) |

### Enums (todos native_enum=False, String + CHECK)

PipelineStatus, PipelineRunStatus, CheckpointStatus, SkillCategory, SkillType,
CustomToolStatus, MCPTransport, MCPStatus, KnowledgeScope, KnowledgeSource,
KnowledgeDocSource, KnowledgeDocStatus, RivvnContractStatus, RivvnStatus,
IntegrationType, IntegrationStatus, ArtifactType, ApprovalStatus,
NotificationChannel, EdgeType

### Sessão (agent-orchestrator/app/db/session.py)

- `engine`: async engine (asyncpg), pool_pre_ping=True
- `async_session_factory`: async_sessionmaker, expire_on_commit=False
- `Base`: DeclarativeBase
- `get_session()` / `get_db`: async generator, yield AsyncSession

### Migration (agent-orchestrator/alembic/)

- `env.py`: async (asyncpg, run_sync), target_metadata=Base.metadata, compare_type=True, include_object ignora tabelas LangGraph + índice HNSW
- `versions/36713ee2fb69_initial_schema.py`: CREATE EXTENSION vector, 17 tabelas, índice HNSW, downgrade simétrico
- `script.py.mako`: template padrão

### Seed (agent-orchestrator/app/db/seed.py)

- `python -m app.db.seed`: cria admin se ADMIN_EMAIL + ADMIN_PASSWORD presentes
- Idempotente (SELECT antes de INSERT)
- owner_id = id (self-referente)
- hash_password de app.core.security (bcrypt custo 12)

### Testes (agent-orchestrator/tests/)

- `conftest.py`: fixture de banco de teste isolado (agent_portal_test_<uuid>)
- `test_models.py`: 18 testes (import, create_all, vector(1536), bcrypt, CRUD por entidade, unicidade por owner)
- `test_migration.py`: 6 testes (upgrade cria tabelas, vector(1536), HNSW, extensão, metadata match, alembic check)
- `test_seed.py`: 5 testes (cria admin, idempotente, sem email, sem password, default name)

## Contratos públicos

### Importar models
```python
from app.db.models import (
    User, Agent, Pipeline, PipelineNode, PipelineEdge, PipelineRun,
    Checkpoint, Skill, CustomTool, MCPServer, KnowledgeBase,
    KnowledgeDocument, KnowledgeChunk, ApprovalRequest, Artifact,
    Integration, RivvnConnection,
)
```

### Sessão
```python
from app.db.session import Base, engine, async_session_factory, get_session, get_db
```

### Seed
```python
# Executável: python -m app.db.seed
# Testável: from app.db.seed import _seed
```

### Campos importantes para os nós seguintes

- **PipelineNode.agent_snapshot** (JSONB): exatamente os campos da spec 4.2 AgentSnapshot (agentId, version, name, description, prompt, strategy, skills, tools, mcpServers, knowledge, integrations, inputs, outputs, actions, model, maxIterations, timeout, shellAccess). SEM capabilities.
- **PipelineEdge**: type (flow/data), source/target (UUID = PipelineNode.id), condition (JSONB EdgeCondition), requires_approval (bool), approval_channel, approval_message, data_mapping (JSONB DataMapping), reject_target (string, ADR-006).
- **Pipeline.entry_node_id**: UUID, explícito (ADR-010).
- **Checkpoint.meta**: mapeia para coluna "metadata" (JSONB).
- **KnowledgeChunk.embedding**: Vector(1536), índice HNSW vector_cosine_ops.
- **ApprovalRequest**: idempotência por (pipeline_id, node_id, checkpoint_id). checkpoint_id = interruptId do LangGraph.

## Comandos para subir e testar

```bash
# Subir o stack (revisor)
docker compose up -d --build

# Rodar migrations manualmente
docker compose exec orchestrator alembic upgrade head

# Rodar seed
docker compose exec orchestrator python -m app.db.seed

# Rodar testes (dentro do container)
docker compose exec orchestrator python -m pytest -q

# A partir de worktree (nós de implementação)
docker compose -p squad-agentica run --rm --no-deps orchestrator python -m pytest -q
```

## Ressalvas

1. **mypy**: 22 erros `valid-type` em `app/db/models.py` (padrão SQLAlchemy 2 `Enum(...)` não tratado como tipo pelo mypy). Não bloqueante; o código existente `app/core/llm.py` também tem erro mypy prévio.
2. **Entrypoint race condition**: o `alembic upgrade head || true` no entrypoint pode falhar silenciosamente se o Postgres ainda não está pronto no primeiro boot. Na prática o `depends_on: postgres: condition: service_healthy` resolve, mas se o Postgres demorar mais que o timeout do healthcheck, a migration falha e o `|| true` engole o erro. Não é um bug dos nós de DB; é uma limitação do entrypoint (dono: infra-docker).
3. **NotificationChannel "in-app"**: o valor usa hífen ("in-app"), consistente com a spec §7.3. Se o frontend precisar de um valor diferente, ajustar no model.

## Merge commits

- db-models: `ae6b70d`
- db-migrations: `cbc2a46`
- db-seed: `a831748`
