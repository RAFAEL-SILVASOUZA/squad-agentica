# D3 — Modelo de Dados & API Base

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 2 · Base de Dados & API**. Dependência: **D1** (infra), **D2** (auth).
> Base: spec (seção 4 "Modelo de Dados", seção 9 "API", seção 11 "Estrutura de Repositórios") + plano.

## Objetivo

Modelar todo o schema do PostgreSQL (SQLAlchemy + Alembic) a partir das interfaces TypeScript da spec (seção 4), expor os routers REST base (stubs) para todos os recursos da seção 9, e entregar ao portal os tipos TypeScript + API client + WebSocket base.

## Escopo (o que FAZ)

- SQLAlchemy models para: `Agent`, `Pipeline`, `PipelineNode`, `PipelineEdge`, `PipelineRun`, `Checkpoint`, `Skill`, `CustomTool`, `MCPServer`, `KnowledgeBase`, `KnowledgeDocument`, `ApprovalRequest`, `RivvnConnection`, `Integration`, `Artifact`.
- Migration Alembic inicial com todo o schema.
- Routers FastAPI vazios/stubs para todos os endpoints da seção 9 (respondem 200/501, sem lógica de negócio — D4–D9 preenchem).
- `lib/types.ts` no portal com todas as interfaces da spec (Agent, Pipeline, PipelineNode, PipelineEdge, DataMapping, EdgeCondition, Skill, CustomTool, MCPServer, KnowledgeBase, KnowledgeDocument, ApprovalRequest, RivvnConnection, PortDef, etc.).
- `lib/api.ts`: wrapper fetch com JWT (busca token em `/api/jwt` e injeta no header), error handling.
- `lib/websocket.ts`: conexão WebSocket nativo (browser API), reconnect, definição dos canais.

## Escopo (o que NÃO FAZ)

- NÃO implementa lógica de CRUD com validação de negócio (D4–D9 fazem). Os routers são stubs que respondem estrutura.
- NÃO implementa compiler, runtime, RAG, notificações.
- NÃO cria UI (só os tipos + client que o D10 consome).
- NÃO altera o schema depois de congelado sem versionar migration nova.

## Dependências

- **D1:** Postgres com `agent_portal` e extensão `vector`, `DATABASE_URL` no env.
- **D2:** `get_current_user` pronto pra proteger os routers.

## Arquivos que OWNS

```
agent-orchestrator/
  app/db/models.py            (SQLAlchemy models)
  app/db/session.py           (engine, sessionmaker, Base)
  app/db/migrations/          (alembic: migration inicial)
  app/api/                    (routers: pipelines, agents, skills, knowledge, mcp_servers, integrations, tools, approvals)
agent-portal/
  lib/types.ts                (todos os tipos da spec)
  lib/api.ts                  (client autenticado)
  lib/websocket.ts            (conexão + canais)
```

## Tarefas

### 3.1 SQLAlchemy models
- Mapear cada interface da seção 4 da spec em um model. Usar `JSON`/`JSONB` para campos flexíveis (`config`, `state`, `metadata`, `discoveredTools`, `env`, `context`).
- `PipelineEdge`: campo `type` (flow/data), `condition` como JSONB (EdgeCondition), `dataMapping` como JSONB.
- `PipelineNode`: `agentSnapshot` como JSONB (cópia imutável do agente). **Nota:** `capabilities` NÃO é um campo do snapshot. É derivado em runtime pelo loader (D8). O snapshot persiste apenas: `agentId`, `version`, `prompt`, `skills`, `tools`, `mcpServers`, `knowledge`, `integrations`, `inputs`, `outputs`, `actions`, `model`, `maxIterations`, `timeout`, `shellAccess`.
- `Checkpoint`: `state` como JSONB.
- `ApprovalRequest`: `context` como JSONB, `attemptedChannels` como ARRAY.
- `RivvnConnection`: `contractStatus` como enum, `scope` como ARRAY.
- `KnowledgeBase`: campos `scope` (enum: global/agent/pipeline), `scopeRef` (FK opcional para agentId ou pipelineId), `source` (enum), `reference` (string), `chunkSize`/`chunkOverlap`/`topK`/`similarityThreshold` (int/float com defaults 512/64/5/0.7), `embeddingModel` (string), `embeddingDim` (int), `documentCount` (int).
- `KnowledgeDocument`: FK `knowledgeBaseId`, `name`, `source` (enum: upload/url), `url` (opcional), `size` (int), `chunkCount` (int), `status` (enum: processing/ready/failed).
- `PipelineRun`: FK `pipelineId`, `threadId` (string, convenção: `f"{pipelineId}:{runId}"`), `status` (enum: running/paused/completed/failed/cancelled), `currentCheckpointId` (string, opcional), `startedAt` (datetime), `completedAt` (datetime, opcional), `error` (text, opcional).
- `Integration`: FK `ownerId`, `type` (enum: github/azure/gitlab, V1: apenas github), `name` (string), `config` (JSONB, type-specific), `status` (enum: active/disabled), `createdAt`, `updatedAt`.
- `Artifact`: FK `runId`, `nodeId` (string), `name` (string), `type` (enum: code/document/image/other), `content` (TEXT, limite 10MB na V1), `size` (int, bytes), `createdAt` (datetime).
- **Tabela de chunks (pgvector):** coluna `embedding vector(1536)` (V1: OpenAI `text-embedding-3-small`). A dimensão é fixa na V1. Fallback local (384 dims) é V2.
- Aceite: models importam e mapeiam sem erro.

### 3.2 Alembic migration inicial
- `alembic revision --autogenerate` gera migration com todo o schema. `alembic upgrade head` roda limpo.
- Coluna `embedding vector(1536)` na tabela de chunks (V1: OpenAI apenas). Índice HNSW: `CREATE INDEX idx_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)`.
- O container roda `alembic upgrade head` no startup (ver D1 §1.7 entrypoint).
- Aceite: banco vazio → `alembic upgrade head` cria todas as tabelas + índice HNSW.

### 3.3 Routers base (stubs)
- Um router por recurso (seção 9 da spec). Cada endpoint responde 200 com estrutura vazia/placeholder ou 501 Not Implemented.
- Todos os routers usam `Depends(get_current_user)`.
- Registrar routers no `main.py`.
- Aceite: `GET /api/agents` (e todos os outros) responde 200/501 com JWT válido, 401 sem.

### 3.4 Tipos TypeScript
- Transladar TODAS as interfaces da seção 4 da spec para `lib/types.ts` (Agent, PortDef, SkillRef, ToolRef, MCPServerRef, KnowledgeRef, IntegrationRef, Pipeline, PipelineNode, AgentSnapshot, PipelineEdge, DataMapping, EdgeCondition, PipelineRun, Checkpoint, Skill, CustomTool, MCPToolInfo, KnowledgeBase, KnowledgeDocument, ApprovalRequest, RivvnConnection, Integration, Artifact, NotificationChannel, etc.).
- Aceite: `tsc --noEmit` passa sem erro.

### 3.5 API client
- `lib/api.ts`: `api.get/post/put/delete` que buscam JWT em `/api/jwt` (cache em memória) e injetam `Authorization: Bearer`. Tratam 401 (redirect signin) e 4xx/5xx.
- Aceite: chamada `api.get('/api/agents')` retorna resposta da API com auth automático.

### 3.6 WebSocket base
- `lib/websocket.ts`: `connectWebSocket()` usando WebSocket nativo (browser API `new WebSocket(url)`), reconnect automático, registro de handlers por canal.
- Formato de mensagem: frames JSON `{ channel: string, data: any }`. O servidor envia e o cliente recebe nesse formato.
- Definir constantes dos canais (seção 9.7 da spec): `pipeline:status`, `pipeline:log`, `approval:new`, `approval:resolved`, `agent:output`.
- Autenticação: token JWT passado no query string do WebSocket URL (`ws://host/ws?token=JWT`). O servidor valida no handshake.
- Aceite: conexão estabelecida, reconnect tenta N vezes, mensagens chegam no formato `{ channel, data }`.

## Critérios de aceite (DoD)

- [ ] Migrations rodam limpo (`alembic upgrade head`)
- [ ] Todos os endpoints da spec (seção 9) respondem (stub 200/501)
- [ ] Tipos TypeScript compilam sem erro
- [ ] API client faz request autenticado com sucesso

## Contratos de interface (o que entrega aos outros)

- **Para D4:** models `Agent`, `PipelineNode`/`AgentSnapshot` prontos; router `/api/agents` pra preencher; tipo `Agent` no `types.ts`.
- **Para D5:** models `Pipeline`, `PipelineNode`, `PipelineEdge`, `PipelineRun`, `DataMapping`, `EdgeCondition`; router `/api/pipelines`; tipos correspondentes.
- **Para D6:** model `Checkpoint`; router `/api/pipelines/:id/checkpoints`.
- **Para D7:** model `ApprovalRequest`; router `/api/approvals`.
- **Para D8:** models `Skill`, `CustomTool`, `MCPServer`, `MCPToolInfo`, `Integration`, `Artifact`; routers `/api/skills`, `/api/tools`, `/api/mcp-servers`, `/api/integrations`, `/api/artifacts`.
- **Para D9:** models `KnowledgeBase`, `KnowledgeDocument`, `RivvnConnection`; router `/api/knowledge` (CRUD completo: POST/GET/PUT/DELETE + upload + documents + query), `/api/integrations/rivvn`.
- **Para D10:** `types.ts` completo, `api.ts`, `websocket.ts` prontos pra consumir.

## Riscos

- JSONB vs colunas tipadas: decidir quais campos são estruturados (ex: `condition`, `dataMapping`) vs livre (`config`, `state`). Recomendo JSONB para flexibilidade, mas validar o contrato no compiler (D5).
- Migration inicial congelada: qualquer mudança futura exige nova migration (D4–D9 respeitam isso).
