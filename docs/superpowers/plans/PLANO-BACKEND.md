# PLANO-BACKEND — Implementação do Backend (Orquestrador + Worker)

> **Nível:** plano de implementação que traduz o `CONTRATO-TECNICO.md` em blocos por nó, para os agentes de infra, banco, auth, backend, pipeline, runtime e HITL deste flow seguirem.
> **Precedência:** em caso de conflito, vale o de maior precedência na ordem do contrato (§13 do contrato): (a) `CONTRATO-TECNICO.md`, (b) spec `2026-09-17-agent-portal-design.md`, (c) domínios D1–D10 + `2026-09-21-execution-plan.md`, (d) este plano / `PLANO-FRONTEND.md` / `DESIGN-SYSTEM.md`, (e) este prompt.
> **Branch de trabalho:** `flow/agent-portal-dev`.
> **Dono deste arquivo:** agente **Plano de Backend** (tech lead de backend).

---

## Contratos que este plano deriva (leitura obrigatória por cada nó)

- `CONTRATO-TECNICO.md` seções 0, 1, 2, 4, 5, 6 (ADR-001 a ADR-010), 7, 8, 9, 13.
- Spec `2026-09-17-agent-portal-design.md` seções 4 (modelos), 5 (execução), 6 (skills/tools/mcp), 7 (knowledge), 8 (integrações), 9 (API), 14 (segurança/concorrência).
- Domínios D1–D9 (nenhum D10: o frontend é de outro agente).
- `2026-09-21-execution-plan.md`.

**Escopo deste plano:** só o **orquestrador** (`agent-orchestrator/`) e o **agent-worker** (`agent-worker/`). Nenhum arquivo do portal (`agent-portal/`) é planejado aqui — cada contrato de API que expomos lista o caminho exato da rota e o payload para o agente frontend. Arquivos compartilhados do portal (`package.json`, `package-lock.json`, `tsconfig.json`, `next.config.ts`) são de `infra-docker`; este plano nunca os toca.

---

# 1. Serviços, portas, variáveis de ambiente e ordem de startup

> Este bloco deriva da §2 do contrato. Os nós `infra-*` constroem isto.

### 1.1 Tabela de serviços (`docker-compose.yml`, dono: `infra-docker`)

| Serviço | Nome no compose | Interna | Publicada | Imagem | Porta do entrypoint |
|---|---|---|---|---|---|
| NGINX (público) | `nginx` | :80 | **:80** | `nginx:1.27-alpine` | `/etc/nginx/nginx.conf` |
| Portal | `portal` | :3000 | não | `node:20-alpine` | `next dev --0.0.0.0:3000` (dev) |
| Orquestrador | `orchestrator` | :8000 | não | `python:3.11-slim` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Agent-Worker | `agent-worker` | :9000 | não | `python:3.11-slim` | `uvicorn app.main:app --host 0.0.0.0 --port 9000` |
| Postgres | `postgres` | :5432 | **:15432** | `pgvector/pgvector:pg15` | — |
| MinIO | `minio` | :9001 / :9002 | **:19001** / **:19002** | `minio/minio:RELEASE.2024.09.22T01.12.59Z` | `minio server /data --console-address ":9002"` |

**Healthchecks (por serviço, no compose):**
- `postgres`: `pg_isready -U agent_portal` (healthcheck nativo, espera a extensão `vector` — a imagem já traz).
- `minio`: binário `mc health` via container auxiliar `minio/mc`, ou `curl` para `http://minio:9001/minio/health/live`.
- `orchestrator`: `curl -f http://orchestrator:8000/health` (GET 200). O container também expõe `GET /api/health` (o NGINX roteia `/api/*` para o orchestrator mantendo o prefixo).
- `agent-worker`: `curl -f http://agent-worker:9000/health` (GET 200).
- `portal`: `curl -f http://portal:3000/` (GET 200/307).

**`depends_on` com condição de saúde (`condition: service_healthy`):**
- `orchestrator` depende de `postgres` e `minio` (saudáveis). O orchestrador **não** depende do NGINX (ele não fala com o NGINX para o banco/MinIO; só o worker-client fala com o NGINX em runtime).
- `agent-worker` depende de `minio` (saudável).
- `portal` depende de `orchestrator` e `postgres` (saudáveis).
- `nginx` depende de **todos** os demais (saudáveis).

> **Decisão mínima coerente (furando um ponto do contrato, registrado em "Furos no contrato"):** o `.env.example` do contrato usa `postgresql+psycopg://` mas a §3 lista `asyncpg` e `psycopg[binary]`. O contrato é claro em usar **SQLAlchemy 2 async + asyncpg**, então a `DATABASE_URL` correta é `postgresql+asyncpg://agent_portal:agent_portal@postgres:5432/agent_portal`. Mantida a URL do `.env.example` (que aponta para o container), apenas alterando o driver de `psycopg` para `asyncpg` e o usuário de `agent_portal` (conforme `postgres/init.sql` abaixo). Ver `postgres/init.sql` no bloco `infra-postgres`.

### 1.2 Variáveis de ambiente por serviço (`docker-compose.yml` / `.env.example`, dono: `infra-docker`)

Derivadas da §2.4 do contrato. O `.env.example` completo do contrato é fonte de verdade; aqui listamos **onde cada serviço consome** cada var (o `.env` compartilhado na rede do compose distribui para todas as que precisam).

| Var | Orchestrator | Worker | Portal | Postgres | MinIO | NGINX |
|---|---:|---:|---:|---:|---:|---:|
| `DATABASE_URL` | ✅ (asyncpg) | – | – | ✅ (`POSTGRES_PASSWORD`) | – | – |
| `JWT_SECRET` | ✅ | – | ✅ (mesmo valor) | – | – | – |
| `NEXTAUTH_SECRET` | – | – | ✅ (mesmo valor) | – | – | – |
| `NEXTAUTH_URL` | – | – | ✅ | – | – | – |
| `WORKER_TOKEN` | ✅ (envia no header) | ✅ (valida) | – | – | – | ✅ (repassa) |
| `MINIO_ROOT_USER` | ✅ | ✅ | – | – | ✅ | – |
| `MINIO_ROOT_PASSWORD` | ✅ | ✅ | – | – | ✅ | – |
| `MINIO_ENDPOINT` | ✅ | ✅ | – | – | ✅ (entry) | – |
| `MINIO_BUCKET_AGENTS` | ✅ | ✅ | – | – | ✅ | – |
| `MINIO_BUCKET_SKILLS` | ✅ | ✅ | – | – | ✅ | – |
| `MINIO_HOST_ENDPOINT` | ✅ (console/host) | ✅ | – | – | ✅ | – |
| `ADMIN_EMAIL` | ✅ (seed) | – | – | – | – | – |
| `ADMIN_PASSWORD` | ✅ (seed, bcrypt 12) | – | – | – | – | – |
| `ADMIN_NAME` | ✅ (seed) | – | – | – | – | – |
| `LLM_PROVIDER` | ✅ | ✅ | – | – | – | – |
| `OPENAI_API_KEY` | ✅ (só se openai) | ✅ (só se openai) | – | – | – | – |
| `EMBEDDING_PROVIDER` | ✅ | ✅ | – | – | – | – |
| `EMBEDDING_DIM` | ✅ (1536) | ✅ (1536) | – | – | – | – |
| `CORS_ORIGINS` | ✅ | – | – | – | – | – |
| `SMTP_*` (5 vars) | ✅ (desligado) | – | – | – | – | – |
| `ENABLE_EMAIL_NOTIFICATIONS` | ✅ | – | – | – | – | – |
| `RIVVN_*` (4 vars) | ✅ (gateado) | – | – | – | – | – |

> **Decisão coerente (furando ponto do contrato, registrado em "Furos no contrato"):** o `.env.example` do contrato lista `EMBEDDING_DIM=1536` e não tem var para o provider de embedding local. O contrato §3/§7 já decide V1 só OpenAI para embeddings. **Nenhuma** var de embedding local é planejada. O provedor mock (`EMBEDDING_PROVIDER=mock`) sustenta todos os testes; com chave real, entra o OpenAI.

### 1.3 Ordem de startup (sequência lógica, não ordem física forçada)

1. `postgres` sobe, `vector` pronta (imagem), DB `agent_portal` criado (via `POSTGRES_DB` ou `postgres/init.sql`).
2. `minio` sobe; container de init (`minio/init-buckets.sh` via `minio/mc`) cria os buckets `agents` e `skills`.
3. `orchestrator` sobe: entrypoint roda `alembic upgrade head` **tolerando a inexistência temporária de tabelas** (retry até o Postgres estar disponível), depois o **seed** (`python -m app.db.seed`), depois o `uvicorn`. **Não** cria agente/skill/tool/pipeline: só o admin (contrato §0).
4. `agent-worker` sobe com `/health` vivo.
5. `portal` sobe com `next dev`.
6. `nginx` sobe por último, só quando todos os upstreams estão healthy.

### 1.4 Entrypoint do orchestrator (dono: `infra-docker`)

```bash
# entrypoint do container orchestrator (no Dockerfile, dono infra-docker)
wait-for-postgres; alembic upgrade head; python -m app.db.seed; exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

O `alembic` e o seed são responsabilidade de `db-migrations` / `db-seed`; o `infra-docker` só **invoca** isto no Dockerfile (contrato §1, §4).

---

# 2. Blocos por nó de implementação

> Cada bloco: objetivo, arquivos (caminhos canônicos do §1), contratos que expõe (assinaturas/rotas/payloads), contratos que consome, critérios de aceite testáveis, testes obrigatórios. Exemplos de payload seguem o envelope do contrato §8 e camelCase.

---

## 2.1 infra-docker

**Objetivo:** chão executável. Scaffold dos três repositórios, Dockerfiles, compose, `.env.example`, `.gitignore/.dockerignore/.gitattributes`, `main.py` com **descoberta automática de routers**, `app/core/*` (config, security, errors, llm, embeddings), skeleton de `alembic/` + `tests/`, health dos workers. Nenhum endpoint de negócio é criado (routers de negócios são de D4–D9, criados por outros nós em `app/api/`).

**Arquivos que cria (dono único, contrato §1):**
- Raiz: `docker-compose.yml`, `docker-compose.override.yml`, `.env.example`, `.dockerignore`, `.gitignore`, `.gitattributes`.
- `agent-orchestrator/{app/__init__.py, app/main.py, pyproject.toml, Dockerfile, alembic.ini, alembic/env.py, alembic/versions/._skeleton, tests/}`
- `agent-orchestrator/app/core/{config.py, security.py, errors.py, llm.py, embeddings.py}`
- `agent-worker/{app/__init__.py, app/main.py, pyproject.toml, Dockerfile, tests/}` (scaffold com `/health` e `/execute` stub que responde 501).
- `agent-portal/{app/page.tsx, app/layout.tsx, package.json, package-lock.json, tsconfig.json, next.config.ts}` (placeholders: página "Agent Portal"; layout com import de `globals.css`).

**Contratos que expõe (o que os outros consomem):**
- `GET /health` (container) → 200 `{ "status": "ok" }`.
- `GET /api/health` → 200 (via NGINX, mesmo handler).
- `app.core.config.settings` → objeto `Settings` (pydantic-settings) com `database_url`, `jwt_secret`, `minio_endpoint`, `llm_provider`, etc. Tipagem: `Settings(BaseModel)`.
- `app.core.security.hash_password(password: str) -> str`, `verify_password(password: str, hash: str) -> bool` (bcrypt custo 12).
- `app.core.errors.*` → envelope de erro (função de exception handler que devolve `{ "error", "code", "details?" }` com o status HTTP).
- `app.core.llm.get_llm_client() -> LLMClient` + interface `LLMClient.chat(messages: list[dict]) -> str` + provider `MockLLMClient` (determinístico).
- `app.core.embeddings.get_embedder() -> Embedder` + interface `Embedder.embed(text: str) -> list[float]`, `embed_batch`, `.dim` + provider `MockEmbedder` (vetor normalizado da dimensão `EMBEDDING_DIM`).
- **Descoberta de routers:** `app/main.py` itera `app/api/*.py` via `importlib`, inclui todo módulo que exponha `router = APIRouter(...)`. `APIRouter(prefix="/api")` — o prefixo `/api` é comum a todos os routers; o `main.py` **não** prefixa de novo, cada router usa `router = APIRouter()` e as rotas vivem em `app/api/<dominio>.py` com os caminhos relativos ao recurso (ex.: `agents.py` define `/`, `/api/agents/{id}`, etc., e o `APIRouter` de cada router recebe `prefix="/api"` ou o `main.py` adiciona `/api`). **Decisão coerente:** `main.py` cria uma única `APIRouter(prefix="/api")` e faz `app.include_router(router)` + inclui os routers encontrados (que declaram suas rotas sem o `/api` no início). Assim `/api/agents`, `/api/pipelines`, etc. funcionam. Documentado no README de `infra-docker`.
- **Health do worker:** `agent-worker/app/main.py` expõe `GET /health` → 200 e `POST /execute` → 501 stub (preenchido por `rt-worker`).

**Contratos que consome:** nenhum contrato de outro nó (primeira fase). Consome só env vars do `.env.example`.

**Critérios de aceite testáveis:**
- `docker compose run --rm orchestrator curl -f http://localhost:8000/health` → 200 (ou test com `httpx` no container).
- `docker compose run --rm agent-worker curl -f http://localhost:9000/health` → 200.
- Um router criado manualmente em `app/api/_infra_probe.py` com `router = APIRouter()` e `@router.get("/probe")` aparece em `GET /api/probe` → prova que a descoberta funciona; **remover antes de entregar**.
- `app/core/security.hash_password`/`verify_password` fazem round-trip.
- `MockLLMClient.chat` devolve string determinística; `MockEmbedder.embed` tem `dim == EMBEDDING_DIM` e normalizado.
- Ruff + mypy/passam no orchestrator e worker.

**Testes obrigatórios:** `tests/test_health.py` (health 200), `tests/test_router_discovery.py` (router adicionado dinamicamente aparece em `/api/probe`), `tests/test_security.py` (bcrypt round-trip, custo 12), `tests/test_llm_mock.py`, `tests/test_embeddings_mock.py`. Todos rodam **dentro do container** (`docker compose run --rm orchestrator pytest`).

---

## 2.2 infra-postgres

**Objetivo:** DB `agent_portal` + extensão `vector` prontas para o D3.

**Arquivos que cria:** `postgres/init.sql`, `postgres/README.md`.

**Contrato que expõe (o que o D3 consome):**
- DB `agent_portal` (via `POSTGRES_DB=agent_portal` no compose + `postgres/init.sql`).
- Usuário `agent_portal` com senha `agent_portal` (conforme `DATABASE_URL`) + **permissão de criar bancos** (para o fixture de teste ger `agent_portal_test_<uuid>`), ex.: `GRANT CREATE ON DATABASE agent_portal TO agent_portal;` + `GRANT ALL ON SCHEMA public TO agent_portal;`.
- `CREATE EXTENSION IF NOT EXISTS vector;` (a imagem `pgvector/pgvector:pg15` já traz).
- Índices HNSW **não** são criados aqui — o D3 cria `idx_chunks_embedding_hnsw` na migration (`D3 3.2`). Aqui só a extensão e o DB.

**Contratos que consome:** `.env.example` (`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` não entram; `POSTGRES_PASSWORD` no compose).

**Critérios de aceite:** `docker compose exec postgres psql -U agent_portal -d agent_portal -c "SELECT extname FROM pg_extension;"` mostra `vector`.

**Testes obrigatórios:** um `postgres/README.md` documenta o comando de verificação (verificação manual no container; não há teste unitário de infra de banco aqui).

---

## 2.3 infra-minio

**Objetivo:** buckets `agents` e `skills` criados automaticamente no boot.

**Arquivos que cria:** `minio/init-buckets.sh`, `minio/README.md`.

**Contrato que expõe:**
- Script `minio/init-buckets.sh` (fim de linha LF, `.gitattributes`): `mc alias set local http://minio:9001 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc mb --ignore-existing local/agents local/skills`.
- Executado como dependência de inicialização do MinIO (`depends_on` com `minio/mc` como container de init no compose, dono `infra-docker`), não como service independente.
- Bucket `agents` (artefatos de agentes `.yml`) + bucket `skills` (conteúdo `.md` de skills).

**Critérios de aceite:** `docker compose exec minio mc ls local/` mostra `agents` e `skills`.

**Testes obrigatórios:** verificação manual via `minio/README.md` (infra).

---

## 2.4 infra-nginx

**Objetivo:** entry point único na :80 com a tabela de precedência da §2.2.

**Arquivos que cria:** `nginx/nginx.conf`, `nginx/conf.d/*.conf`, `nginx/README.md`.

**Contrato que expõe (regras de precedência, nesta ordem):**
1. `location = /api/auth`, `location /api/auth/` → `portal:3000` (NextAuth).
2. `location = /api/session-token` → `portal:3000`.
3. `location = /api/ws` (sem `/` final) → **orchestrator:8000** com `WebSocket` upgrade (`proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`), timeouts longos.
4. `location /api/` → `orchestrator:8000/api/` (mantém prefixo `/api`).
5. `location /` → `portal:3000`.

**Bloco interno (não publicado):** `server { listen 8081; location /execute { proxy_pass http://agent-worker:9000/execute; proxy_set_header X-Worker-Token $env_WORKER_TOKEN; } }` — o `WORKER_TOKEN` vem do ambiente do NGINX (§2.4 do contrato). O orchestrator chama `POST http://nginx:8081/execute`.

**Streaming:** os endpoints `POST /api/agents/chat` e `POST /api/agents/{id}/chat` devem ter `proxy_buffering off` + timeouts longos (documentar no `nginx/README.md`; o contrato §8 exige).

**`client_max_body_size`** dimensionado para o upload de knowledge (`client_max_body_size 25m;`).

**Nenhum** rate limiting (o contrato §8/§14.1 diz: rate limiting na aplicação, não no NGINX).

**Critérios de aceite:** `curl http://localhost/api/health` → 200 (orchestrator); `curl http://localhost/` → portal; `curl -H "X-Worker-Token: <token>" http://localhost/execute` (via NGINX) → worker valida. Verificação no host após o revisor subir o stack (não neste nó; o protocolo comum veda `docker compose up`).

**Testes obrigatórios:** nenhum unitário (verificação de routing é manual/container pelo revisor). Documentar no `nginx/README.md` os comandos de verificação.

---

## 2.5 db-models

**Objetivo:** models SQLAlchemy 2 async de **todas** as interfaces da spec §4. Base de Fase 2; consome `db-session` (infra-docker entrega o engine) e `auth-backend` (expõe `get_current_user`).

**Arquivos que cria:** `agent-orchestrator/app/db/models.py`, `app/db/session.py` (o `session.py` é engine/sessionmaker/Base — o `infra-docker` dá o skeleton; o `db-models` preenche as classes e confirma o `Base`/engine).

**Contrato que expõe (classes SQLAlchemy):** derivadas da spec §4 + D3. Nomes de colunas em snake_case; conversão camelCase feita na API (§8). `owner_id` derivado do JWT.

- `User(id: UUID, email: str(unique), name: str, password_hash: str, owner_id: UUID, created_at)`. (`owner_id` = sub do JWT; V1 single-user, seed cria um.)
- `Agent(id, owner_id, name, type, description, prompt, strategy, model, max_iterations:int, timeout:int, shell_access:bool, contract_json: JSONB (inputs/outputs/actions), created_at, updated_at)`. Os ports/actions são **JSONB** (o contrato é flexível; o validator valida o conteúdo).
- `Pipeline(id, owner_id, name, description, status: enum(draft|running|paused|completed|failed), entry_node_id: str, graph_json: JSONB (nodes+edges), current_checkpoint_id:str|null, started_at, completed_at, created_at, updated_at)`.
- `PipelineRun(id, owner_id, pipeline_id:FK, thread_id:str, status: enum(running|paused|completed|failed|cancelled), current_checkpoint_id:str|null, started_at, completed_at, error:text|null)`.
- `Checkpoint(id, owner_id, run_id:FK, node_id:str, state: JSONB, status: enum(completed|interrupted|failed), timestamp, metadata: JSONB)`.
- `Skill(id, owner_id, name, description, category: enum, type:enum(prompt), definition: JSONB, created_at, updated_at)` + conteúdo `.md` no MinIO (**não** é coluna).
- `CustomTool(id, owner_id, name, description, category, script:text, io_json: JSONB (inputs/outputs), version:int, status: enum(draft|deployed|archived), created_at, updated_at)`.
- `MCPServer(id, owner_id, name, description, transport: enum(stdio|sse|http), command:str|null, url:str|null, env: JSONB, status: enum(connected|disconnected|error), last_connected_at, discovered_tools: JSONB, created_at, updated_at)`.
- `KnowledgeBase(id, owner_id, name, description:str|null, scope: enum(global|agent|pipeline), scope_ref:str|null, source: enum(upload|vector-db|url|rivvn), reference:str|null, chunk_size:int=512, chunk_overlap:int=64, top_k:int=5, similarity_threshold:float=0.7, embedding_model:str, embedding_dim:int, document_count:int, created_at, updated_at)`.
- `KnowledgeDocument(id, owner_id, knowledge_base_id:FK, name, source: enum(upload|url), url:str|null, size:int, chunk_count:int, status: enum(processing|ready|failed), created_at)`.
- `RivvnConnection(id, owner_id, contract_status: enum(active|inactive|expired), status: enum(connected|disconnected|expired), connected_at, scope: ARRAY, created_at, updated_at)`.
- `Integration(id, owner_id, type: enum(github|azure|gitlab, V1 github), name, config: JSONB, status: enum(active|disabled), created_at, updated_at)`.
- `Artifact(id, owner_id, run_id:FK, node_id:str, name, type: enum(code|document|image|other), content:text(10MB), size:int, created_at)`.
- `ApprovalRequest(id, owner_id, pipeline_id, agent_id, checkpoint_id, message, context: JSONB, artifacts: ARRAY|null, status: enum(pending|approved|rejected|revised), response:str|null, responded_by:str|null, responded_at:str|null, channel: enum(in-app|email|teams|slack), sent_at:str|null, retry_count:int=0, max_retries:int=3, attempted_channels: ARRAY, fallback_channel: enum|null, timeout_seconds:int)`. **Chave de idempotência do upsert:** `(pipeline_id, node_id, checkpoint_id)` (ADR-009).

**Coluna pgvector:** uma tabela `knowledge_chunk(id, owner_id, knowledge_base_id:FK, chunk_index:int, content:text, embedding vector(1536), created_at)`. Dimensão **fixa 1536** (V1). O índice HNSW é criado na migration pelo `db-migrations` (D3 3.2), não pelo model.

**Contrato que consome:** `app.core.config.settings.database_url` (infra-docker), `app/db/session.py` engine (infra-docker). Nenhum outro nó ainda.

**Critérios de aceite:** `from app.db.models import Agent, Pipeline, ...` importa sem erro; `Base.metadata.create_all(engine)` cria todas as tabelas + `knowledge_chunk.embedding` como `vector(1536)`.

**Testes obrigatórios:** `tests/test_models.py`: (a) importar todos os models; (b) `create_all` em banco de teste gera todas as tabelas; (c) `knowledge_chunk.embedding` tem tipo `vector` (via reflection); (d) instanciar `User(password_hash=...)` com hash bcrypt válido passa em `verify_password`. Banco de teste isolado (fixture `agent_portal_test_<uuid>`, D3 4/protocolo comum).

---

## 2.6 db-migrations

**Objetivo:** Alembic configurado (env.py) + migration inicial `0001_initial.py` com **todo** o schema (o `infra-docker` dá o skeleton `alembic/`; o `db-migrations` preenche env.py + a migration).

**Arquivos que cria/altera:** `agent-orchestrator/alembic/env.py`, `alembic/versions/0001_initial.py`.

**Contrato que expõe:** migration idempotente ao rodar `alembic upgrade head` no boot.

**Contrato que consome:** `app.db.models.Base` (db-models) para autogeração + `app.core.config.settings.database_url` (infra-docker).

**Critério de aceite:** `alembic upgrade head` em banco vazio (de teste) cria todas as tabelas; `alembic current` reporta `head`.

**Testes obrigatórios:** `tests/test_migration.py`: (a) drop do schema, `alembic upgrade head`, `create_all` comparada via `MetaData` dos models → tabelas equivalentes; (b) `knowledge_chunk.embedding` permanece `vector(1536)` após a migration. Banco de teste isolado.

---

## 2.7 db-seed

**Objetivo:** **único** seed do sistema: o usuário admin. **Nunca** cria agente/skill/tool/pipeline (contrato §0).

**Arquivos que cria:** `agent-orchestrator/app/db/seed.py`.

**Contrato que expõe (comportamento):**
- `python -m app.db.seed` cria um `User` (`ADMIN_EMAIL`/`ADMIN_PASSWORD` bcrypt custo 12, `ADMIN_NAME`) **só se** `ADMIN_EMAIL` **e** `ADMIN_PASSWORD` estiverem presentes (`app.core.config.settings.admin_*`); se faltarem, sai sem criar nada.
- Idempotente: se já existe um admin com o mesmo `email`, não recria (não quebra reboots).
- `owner_id` do admin = sub do JWT que o `auth-backend` emitir. **Decisão coerente:** o seed não sabe o sub de antemão (ainda não há login); armazena o `email` e, no `auth-backend`, o `sub` do JWT é igual ao `owner_id` (V1 single-user, contrato §11.19). O seed grava `owner_id` como o UUID do próprio admin (`id`) como placeholder válido de FK, e documenta que o `sub==owner_id`.

**Critério de aceite:** após o entrypoint rodar o seed, `SELECT count(*) FROM users` == 1 (ou 0 se env em falta). Reboot não duplica.

**Testes obrigatórios:** `tests/test_seed.py`: (a) env com admin → cria 1 usuário; (b) env sem admin → cria 0; (c) re-execução com admin já existente → continua 1 (não duplica). Banco de teste isolado.

---

## 2.8 auth-backend

**Objetivo:** auth no orchestrador. JWT de delegação, `get_current_user` (opt-out), roteação de refresh, rate limiting do login, hash bcrypt (consoma `app.core.security`).

**Arquivos que cria:** `agent-orchestrator/app/auth/{config.py, service.py, deps.py}, app/api/auth.py`.

**Contrato que expõe (rotas FastAPI, prefixo implícito `/api`):**
- `POST /api/auth/login` → body `{ email, password }` → 200 `{ accessToken, refreshToken }` (JWT assinados) / 401 envelope `{ error:"unauthorized", code:"not_authenticated" }` / 429 rate-limited. Claims: `sub`(ownerId), `iat`, `exp`, `typ` (`"access"`|`"refresh"`); access exp 15 min, refresh exp 7 dias.
- `POST /api/auth/refresh` → body `{ refreshToken }` → 200 `{ accessToken }` / 401 / 429. Rotação: refresh usado é **invalidado** após uso (blacklist em memória por `jti`, V1) — o refresh antigo **não** devolve o mesmo refresh reutilizável.
- `GET /api/auth/me` → 200 `{ userId, email, name }` / 401.
- `GET /api/health`, `GET /api/auth/health` → 200 (health checks opt-out).

**Contrato que consome:** `app.core.security.hash_password/verify_password` (infra-docker), `app.core.config.settings.jwt_secret` (infra-docker), model `User` (db-models). Expõe `get_current_user` (dependência FastAPI global com lista de exceções `/api/auth/*` + healths).

**Critérios de aceite testáveis:** (a) sem token → 401 em qualquer rota protegida; (b) token access válido → 200; (c) token expirado → 401; (d) refresh reutilizado → 401 (invalidado); (e) login com credenciais erradas → 401 genérico (não revela se e-mail existe); (f) 5 tentativas de login em 1 min → 429 envelope (rate limit in-memory por `sub`/IP, V1).

**Testes obrigatórios:** `tests/test_auth.py`: login/refresh/me, rotação de refresh, token expirado, `get_current_user` protege router novo (nasce protegido), envelope de erro 401/429. Banco de teste isolado (só leitura de `User`; o seed pode usar fixture em vez do real).

---

## 2.9 be-agents

**Objetivo:** CRUD de agentes com artefato `.yml` persistido no MinIO (bucket `agents`) + metadados no Postgres, validação de contrato, chat de construção streaming. Fase 4.

**Arquivos que cria:** `agent-orchestrator/app/api/agents.py`, `app/agents/{base.py,builtins.py,validator.py,storage.py}`, `app/agents/{planner.py,developer.py,reviewer.py,deployer.py}`.

**Contrato que expõe (rotas, prefixo `/api`):**
- `POST /api/agents` → body `Agent` (sem `id`) → 201 `Agent` (inclui `id`). Faz PUT `agents/{id}.yml` no MinIO **e** INSERT Postgres (transação compensatória: se MinIO falhar, DELETE Postgres).
- `GET /api/agents?page=&limit=&type=` → 200 `{ items:[Agent], total, page, limit }`.
- `GET /api/agents/{id}` → 200 `Agent` / 404 `agent_not_found`.
- `PUT /api/agents/{id}` → 200 `Agent` / 404 / 409 `graph_running` (há run running da pipeline que usa este agente — ver §8). Faz PUT MinIO + UPDATE Postgres.
- `DELETE /api/agents/{id}` → 204 / 404 / 409 `graph_running`. Faz DELETE MinIO + DELETE Postgres.
- `POST /api/agents/chat` → body `{ message, draftId? }` → **SSE stream** `{ type:"text", data }` / `{ type:"config_update", data:Partial<Agent> }` / `{ type:"done", data:{draftId} }`. Cria sessão efêmera se `draftId` ausente.
- `POST /api/agents/{id}/chat` → body `{ message }` → **SSE stream** (edição).
- **Validação** (`POST`/`PUT`): `inputs`/`outputs` com `name` único, `type` ∈ whitelist (`document|code|artifact|signal`), `actions` ∈ `{follow,return,finalize}`. Inválido → 400 `{ error:"validation error", code:"invalid_graph", details:{ errors:[{rule,message,nodeId?,edgeId?}] } }`.

**Contrato de execução (consome base + loader, entrega ao runtime):**
- `async Agent.run(inputs: dict, capabilities: AgentCapabilities) -> dict` (base.py). Recebe `AgentCapabilities` como parâmetro (não lê do snapshot). Built-ins: planner/developer/reviewer/deployer com prompt default não-vazio.

**Contrato que consome:** `app.core.security` (bcrypt), model `Agent` (db-models), `app.core.llm.get_llm_client()` (infra-docker), storage MinIO (`be-agents` own storage.py — contrato de serviço), minio creds (env). `loader.load()` vem de `be-loader` (FASE 5).

**Critérios de aceite testáveis:** (a) criar agente → .yml presente no MinIO + INSERT Postgres; (b) atualizar/remover sincroniza os dois; (c) MinIO em falta → 500 envelope (rollback Postgres feito); (d) contrato inválido → 400 com `details.errors`; (e) chat devolve SSE com eventos; (f) `Agent.run` com mock LLM devolve output estruturado verificável.

**Testes obrigatórios:** `tests/test_agents_crud.py` (create/list/get/update/delete + MinIO mock), `tests/test_agents_validator.py` (todas as regras de port/action), `tests/test_agents_storage.py` (round-trip .yml), `tests/test_agents_base.py` (built-ins executam). Banco de teste isolado + MinIO mock (`httpx`/`minio` fake).

---

## 2.10 be-skills

**Objetivo:** skills (registry + storage MinIO bucket `skills`), tools custom (registry + sandbox + validator), servidores MCP (registry + client + validator), com CRUD em routers separados. Fase 4.

**Arquivos que cria:**
- Skills: `app/skills/registry.py`, `app/skills/storage.py`, `app/skills/builtins/` (code-gen, test-runner, security-scanner, doc-writer, api-client, deploy-runner), `app/api/skills.py`.
- Tools: `app/tools/registry.py`, `app/tools/sandbox.py`, `app/tools/validator.py`, `app/tools/builtins/` (read_file, write_file, edit_file, shell, web_search, web_fetch, glob, grep, list_directory), `app/api/tools.py`.
- MCP: `app/mcp/registry.py`, `app/mcp/client.py`, `app/mcp/validator.py`, `app/api/mcp_servers.py`.

**Contratos que expõe (rotas):**
- Skills: `GET/POST /api/skills`, `GET/PUT/DELETE /api/skills/{id}`. CRUD faz PUT/DELETE `skills/{id}.md` no MinIO + DML Postgres (transação compensatória).
- Tools: `GET/POST /api/tools`, `GET/PUT/DELETE /api/tools/{id}`, `POST /api/tools/{id}/deploy`, `POST /api/tools/{id}/test`. Sandbox: subprocesso isolado, timeout 30s default (máx 120s), sem acesso ao filesystem do host, sem secrets em vars. Validator: script compila + contrato de I/O.
- MCP: `GET/POST /api/mcp-servers`, `GET/PUT/DELETE /api/mcp-servers/{id}`, `POST /api/mcp-servers/{id}/test` (chama `tools/list`, atualiza `discovered_tools`). Client: stdio/sse/http.

**Contrato que consome:** model `Skill`/`CustomTool`/`MCPServer` (db-models), storage MinIO (`be-skills` own storage.py), minio creds (env). O **loader** (`app/skills/loader.py`) é criado por `be-loader` (FASE 5) — `be-skills` **não** cria `loader.py`; só o registry/storage/builtins. **Atenção (furando ponto do mapa de fases):** o contrato §9 atribui `app/skills/loader.py` ao `be-loader`, mas `be-skills` **não** cria `loader.py`. `be-skills` entrega registry/storage/builtins; o loader é do `be-loader`. Este bloco respeita isso.

**Critérios de aceite testáveis:** (a) CRUD skills sincroniza MinIO+Postgres; (b) tool custom: criar → validar → deploy → testar; (c) sandbox isola (subprocesso com timeout); (d) MCP: registrar → testar → `discovered_tools` populado; (e) `shell` só com `shellAccess=true` (validação no loader, não aqui).

**Testes obrigatórios:** `tests/test_skills.py`, `tests/test_tools_sandbox.py` (timeout, isola host), `tests/test_tools_validator.py`, `tests/test_mcp_registry.py`, `tests/test_mcp_client_mock.py` (mock do subprocesso MCP). Banco de teste isolado + sandbox/mock.

---

## 2.11 be-knowledge

**Objetivo:** RAG local (upload → chunking → embedding → pgvector → query), CRUD de KnowledgeBase + documentos, gateway Rivvn (gateado por contrato comercial). Fase 4.

**Arquivos que cria:** `app/knowledge/{rag.py,chunker.py,embedder.py}`, `app/knowledge/rivvn/{oauth.py,client.py}`, `app/api/knowledge.py`.

**Contratos que expõe (rotas, prefixo `/api`):**
- `POST /api/knowledge` → 201 `KnowledgeBase` / 400.
- `GET /api/knowledge?scope=&source=` → 200 paginado.
- `GET /api/knowledge/{id}` → 200 / 404 `knowledge_base_not_found`.
- `PUT /api/knowledge/{id}` (name, description, config RAG) → 200 / 404.
- `DELETE /api/knowledge/{id}` → 204 / 404 (remove KB + documentos + vetores da tabela `knowledge_chunk`).
- `POST /api/knowledge/{id}/upload` (multipart, `file`) → 200 `{ documentId }` (indexa: chunk → embed → insert vector). Limitado por rate (10/min, §8).
- `GET /api/knowledge/{id}/documents` → paginado.
- `DELETE /api/knowledge/{id}/documents/{docId}` → 204 / 404.
- `POST /api/knowledge/query` → body `{ query, knowledgeBaseIds[], topK? }` → 200 `{ chunks:[{score, content}] }` (cosine distance `<=>`, top-K).
- Rivvn: `GET /api/integrations/rivvn/authorize` → 307 redirect / **403** se `contractStatus != "active"`; `GET /api/integrations/rivvn/callback` (troca code por token via SDK); `GET /api/integrations/rivvn/status`; `DELETE /api/integrations/rivvn`.

**Contrato de query (entrega ao runtime, consome por D6):** `query(text: str, knowledge_base_ids: list[str], top_k: int) -> list[dict]` (rag.py). Injeção no prompt é do runtime (D6); `be-knowledge` só responde a query.

**Contrato que consome:** model `KnowledgeBase`/`KnowledgeDocument`/`RivvnConnection` + tabela `knowledge_chunk` (db-models), `app.core.embeddings.get_embedder()` (infra-docker), `app.core.llm.get_llm_client()` (mock, só se provider real), pgvector (infra-postgres).

**Critérios de aceite testáveis:** (a) upload → chunk → embed (mock) → vector(1536) inserido; (b) query retorna top-K por cosine distance; (c) Rivvn sem contrato → 403; (d) delete remove vetores.

**Testes obrigatórios:** `tests/test_knowledge_crud.py`, `tests/test_knowledge_rag.py` (mock embedder, vector cos), `tests/test_knowledge_rivvn_gate.py` (403 sem contrato). Banco de teste isolado + mock embedder.

> **Decisão coerente (furando ponto do contrato, registrado):** a §9 do contrato lista `app/api/integrations.py` em **dois** domínios (D9-be-knowledge e D8-be-integrations). Pela convenção de "único dono" e pela §9 do contrato (FASE 4, `be-integrations` = `app/api/integrations.py`), **`app/api/integrations.py` é do `be-integrations`**. O `be-knowledge` **não** cria `app/api/integrations.py`; ele cria `app/api/knowledge.py` e, para o gateway Rivvn, o contrato §9 do contrato também lista `app/api/integrations.py` na D9. **Resolução:** o gateway Rivvn (`authorize/callback/status/DELETE`) **vive em `app/api/integrations.py`, do `be-integrations`**; o `be-knowledge` entrega a lógica de negócio (`knowledge/rivvn/oauth.py`, `client.py`) e consome as rotas via um client interno. Documentado como handoff entre `be-knowledge` e `be-integrations`. (Ver também "Furos no contrato".)

---

## 2.12 be-integrations

**Objetivo:** CRUD de integrações (`Integration`, V1 GitHub leitura) + gateway Rivvn (`authorize/callback/status/DELETE`), exposto como tools ao agente (list_repos, list_pulls, list_issues, get_pr_diff). Fase 4.

**Arquivos que cria:** `app/api/integrations.py`, `app/integrations/{github.py,registry.py}`.

**Contratos que expõe (rotas, prefixo `/api`):**
- CRUD: `GET/POST /api/integrations`, `GET/PUT/DELETE /api/integrations/{id}`. Model `Integration` (`type=github`, `config={owner, repos[]}`).
- GitHub leitura: `GET /api/integrations/github/repos`, `GET /api/integrations/github/repos/{owner}/{repo}/pulls?state=`, `GET /api/integrations/github/repos/{owner}/{repo}/issues?state=&labels=`.
- Rivvn: `GET /api/integrations/rivvn/authorize` (→ 307 / 403 se sem contrato), `GET /api/integrations/rivvn/callback`, `GET /api/integrations/rivvn/status`, `DELETE /api/integrations/rivvn`. (lógica de `oauth.py`/`client.py` vem de `be-knowledge`; este nó só **regista** as rotas que a consomem.)

**Contrato de tools ao agente:** `list_repos(owner)`, `list_pulls(owner,repo,state?)`, `list_issues(owner,repo,state?,labels?)`, `get_pr_diff(owner,repo,number)`. O `be-loader` injeta isto na `AgentCapabilities.tools`.

**Contrato que consome:** model `Integration` (db-models), `GITHUB_TOKEN` (env), gateway logic de `be-knowledge`, Rivvn SDK (mock).

**Critérios de aceite testáveis:** (a) criar integração GitHub → listar repos/PRs/issues; (b) Rivvn sem contrato → 403; (c) `be-loader` expõe as 4 tools a um agente.

**Testes obrigatórios:** `tests/test_integrations_crud.py`, `tests/test_integrations_github_mock.py` (mock httpx), `tests/test_integrations_rivvn_gate.py`. Banco de teste isolado + mock httpx.

---

## 2.13 spike

**Objetivo:** prova de arquitetura do LangGraph (superfície exata de API da versão pinada `langgraph==0.2.61`): streaming (`astream` + `stream.interrupted`/`stream.interrupts`), `interrupt()`, `Command(goto=)`/`Command(resume=)`, `PostgresSaver.setup()`, round-trip de State TypedDict. **Não é produto** — é um experimento que valida pressupostos do compiler/runtime/HITL.

**Arquivos que cria:** `spike/*.py` (scripts autocontidos), `spike/README.md` (resultado + divergências registradas).

**Contrato que expõe (o que o README registra):** (a) a assinatura real de `graph.astream`, (b) como detectar interrupção (`stream.interrupted` vs exceptions), (c) `Command` aceita strings de node id real, (d) `PostgresSaver` cria as tabelas com `setup()`, (e) TypedDict fixo round-tripa no PostgresSaver. **Se** a superfície divergir da §3 do contrato, o spike **regista a divergência** (contrato §13) e **não** contorna.

**Critério de aceite:** o `spike/README.md` confirma (ou corrige) cada pressuposto listado; o runtime/validator/resume implementam contra a superfície **real**.

**Testes obrigatórios:** os scripts do spike que confirmam cada API (coletar a saída no README). Não há `pytest` obrigatório no spike (experimento), mas scripts determinísticos que o revisor roda.

---

## 2.14 pe-validator

**Objetivo:** validador de grafo (regras 1–11 da spec §4.2, com as 3 regras novas do D5). **Não** cria arquivo em `app/api/` (o endpoint de validação vive em `pe-executor` em `app/api/pipelines.py`). Fase 5.

**Arquivos que cria:** `agent-orchestrator/app/compiler/validator.py`.

**Contrato que expõe (assinatura):**
- `validate_graph(pipeline_json: dict) -> list[ValidationResult]` onde `ValidationResult = { rule:int, message:str, nodeId?, edgeId? }`. Lista vazia = grafo válido.
- Regras: (1) data edge exige dataMapping com sourceOutput/targetInput válidos; (2) sourceOutput ∈ outputs do source; (3) targetInput ∈ inputs do target; (4) tipo do port compatível (match exato); (5) data edge pra B + flow edge pra C não é erro; (6) target com input required sem data edge → erro; (7) (transformação, não erro — ver graph_builder) data edge sem flow edge injeta flow incondicional; (8) nó órfão (sem flow nem data de entrada) → erro; (9) entryNodeId inexistente → erro; (10) action sem flow edge com essa condition → **aviso**; (11) flow edges idênticas entre mesmo par → erro.

**Contrato que consome:** modelo de grafo (JSON: `nodes[]`, `edges[]`, `entryNodeId`), `AgentSnapshot.inputs/outputs/actions` (db-models, via cache/leitura do orchestrator). Nenhum model fixo; o validator opera no JSON bruto + snapshots.

**Critérios de aceite:** cada regra testada isoladamente (11 casos). Grafo com data edge sem flow edge **passa na validação** (a injeração é do graph_builder).

**Testes obrigatórios:** `tests/test_validator.py` (11 casos, um por regra). Banco de teste **não** precisa (validação é pura; testes unitários sem DB, ou com seed em memória).

---

## 2.15 pe-loader

**Objetivo:** `loader.load(agent_snapshot) -> AgentCapabilities`. Resolve skills (baixa `.md` do MinIO, injeta prompts no `systemPrompt`), tools (CustomTools deployadas + básicas habilitadas, shell se `shellAccess`), mcpServers (descobre tools via `tools/list`), knowledge (RAG via query). **Fase 5.** O loader roda **no orchestrator** neste plano (ADR-008 diz "loader no worker", mas o mapa de fases do contrato §9 atribui `app/skills/loader.py` ao `pe-loader` no orchestrador; ver "Furos no contrato" para a tensão ADR-008 vs §9).

**Arquivos que cria:** `agent-orchestrator/app/skills/loader.py` (+ modelo `AgentCapabilities` — contrato sugere `app/compiler/state.py` ou `app/agents/*`; **decisão coerente:** `AgentCapabilities` vive em `app/compiler/state.py`, criado por `pe-compiler`, que é a fonte do schema; o loader só o consome). **Atenção:** `be-skills` cria `registry.py/storage.py/builtins/`; `pe-loader` **não** duplica, só consome.

**Contrato que expõe (assinatura):**
- `async load(agent_snapshot: AgentSnapshot) -> AgentCapabilities`
- `AgentCapabilities = { systemPrompt: str, tools: list[dict], mcpTools: list[dict], knowledgeContext: list[str] }` (definido em `app/compiler/state.py`).
- Resolve: (a) skills → `systemPrompt += skill_md`; (b) tools → custom deployadas + básicas (+ shell se `shellAccess`); (c) mcpServers → `tools/list`; (d) knowledge → `query(snapshot.knowledge)`.

**Contrato que consome:** `AgentCapabilities` typealias (pe-compiler), storage MinIO (`be-skills`), tool registry (`be-skills`), mcp registry (`be-skills`), knowledge query (`be-knowledge`).

**Critérios de aceite:** `load(snapshot_planner)` devolve `AgentCapabilities` com `systemPrompt` contendo o prompt + skills; `tools` inclui read_file etc.; shell só se `shellAccess=true`.

**Testes obrigatórios:** `tests/test_loader.py` (mock MinIO storage, mock mcp client, mock knowledge query): (a) skills injetadas, (b) tools corretas, (c) shell condicionada, (d) knowledgeContext populado. Banco de teste não precisa (loader é stateless sobre env/mock).

---

## 2.16 pe-compiler

**Objetivo:** `compile_pipeline(pipeline_json) -> StateGraph` (JSON → LangGraph) + `State` TypedDict fixo + condições. Fase 5. Consome `pe-validator` (valida antes), `hitl-approval` (função do nó de aprovação).

**Arquivos que cria:** `agent-orchestrator/app/compiler/{state.py,graph_builder.py,conditions.py}`. **Não** toca em `app/api/`.

**Contratos que expõe (assinaturas):**
- `State = TypedDict("State", {"data": dict, "actions": dict, "status": dict, "iterations": Annotated[dict, operator.add], "max_iter_exceeded": Annotated[bool, operator.or_], "pipeline_status": str})` (ADR-002, schema **fixo** — nunca `types.new_class()`).
- O namespace por nodeId é **convenção dentro dos valores**: `state["data"][nodeId]` (ADR-003).
- `compile_pipeline(pipeline_json: dict) -> StateGraph` (graph_builder.py): nodes por agente (node functions), entry `add_edge(START, entryNodeId)`, flow edges (incondicionais + condicionais via `route_fn`), fan-out (`{"follow":[A,B]}`), data edges resolvidas no node function (não criam arestas), requiresApproval → `approval_node_{edgeId}` com arestas `source → approval_node → target` (proceed) e `source → approval_node → reject_handler` (ADR-006).
- `build_conditions(route_fn per node) -> Callable[[State], str]` (conditions.py): `field:"action"` só (whitelist), operator `eq/neq/in/not_in`, nunca `eval`.
- `create_approval_node(edge_config: EdgeConfig) -> Callable[[State], Coroutine]` (exporta para o `hitl-approval` registrar a função; o compiler **importa** a função que o HITL entrega). **Decisão coerente:** o `hitl-approval` entrega `approval_node_function`/`create_approval_node`; o compiler **chama** `graph.add_node(f"approval_node_{edgeId}", create_approval_node(edge_config))`.

**Contrato que consome:** validação (`pe-validator`), função do nó de aprovação (`hitl-approval`), snapshots dos nós, `AgentCapabilities` (pe-loader).

**Critérios de aceite testáveis:** (a) A→B→C gera StateGraph com 3 nós + arestas; (b) data edge sem flow edge injeta flow incondicional (regra 7); (c) branch follow vs return; (d) fan-out A→[B,C]; (e) finalize → END; (f) requiresApproval gera `approval_node_{edgeId}` com arestas corretas; (g) mesmo agente em dois nós → State keys namespaced por nodeId sem colisão.

**Testes obrigatórios:** `tests/test_compiler.py`: grafo simples, regra 7, condition/fan-out/finalize, requiresApproval (nó de aprovação + arestas), agente em loop (namespacing). Banco de teste **não** precisa (compilação é pura; LangGraph `StateGraph` não persiste aqui).

---

## 2.17 rt-executor

**Objetivo:** executa o `StateGraph` compilado (pe-compiler) com checkpoints, ciclo de vida execute/pause/resume/stop, delegação ao worker via NGINX, hook de interrupção (upsert ApprovalRequest + notificação), eventos WebSocket. Fase 6. Expõe as rotas de execução.

**Arquivos que cria:** `agent-orchestrator/app/runtime/{executor.py,checkpoint.py,worker_client.py}, app/api/pipeline_runs.py`.

**Contratos que expõe (rotas, prefixo `/api`):**
- `POST /api/pipelines/{id}/execute` → 200 `PipelineRun` / 409 `pipeline_already_running` (body `{ error:"pipeline_already_running", runId }`). Cria novo run, `thread_id = f"{pipelineId}:{runId}"`.
- `POST /api/pipelines/{id}/pause` → 200 (status run `paused`; nó em execução termina, novo nó não inicia).
- `POST /api/pipelines/{id}/resume` → 200 (retoma do último checkpoint).
- `POST /api/pipelines/{id}/stop` → 200 (run `cancelled`, cancela aprovações pendentes, emite `pipeline:status`).
- `GET /api/pipelines/{id}/runs?page=&limit=` → paginado.
- `GET /api/pipelines/{id}/checkpoints` → paginado `Checkpoint[]`.
- `POST /api/pipelines/{id}/checkpoints/{cpId}/resume` → 200 (retoma de checkpoint específico; **não** é o caminho do interrupt de aprovação — ver §7).
- **Nota de rota (resolvido, sem conflito):** o contrato §9 atribui `app/api/pipelines.py` ao `rt-executor` (FASE 6). O `rt-executor` **é** o dono de `app/api/pipelines.py` e nele vivem **todas** as rotas de pipeline: CRUD (`POST/GET/PUT /api/pipelines`, `GET /api/pipelines/{id}`), execução (`POST /api/pipelines/{id}/execute|pause|resume|stop`, `GET /api/pipelines/{id}/runs`, `GET /api/pipelines/{id}/checkpoints`, `POST /api/pipelines/{id}/checkpoints/{cpId}/resume`) e **validação de grafo** (`POST /api/pipelines/validate` — consome `pe-validator`). O `pe-validator` (FASE 5) **não** cria arquivo em `app/api/` (contrato §9 explícito: "consome; não cria arquivo em `app/api/`"); ele entrega só a função `validate_graph()`. O endpoint de validação que consome essa função vive em `app/api/pipelines.py`, do `rt-executor`. Handoff: `pe-validator` exporta `validate_graph`; `rt-executor` a chama no route de validação. **Sem** duplicata de router de pipelines.

**Contrato de execução (consome pe-compiler + pe-loader + hitl-approval):**
- `execute(pipeline_id, run_id)`: compila (pe-compiler) → `astream` com `PostgresSaver(thread_id)` → por nó, node function chama `worker_client.execute(...)`. Detecta interrupção → **upsert** `ApprovalRequest` chave `(pipeline_id, node_id, checkpoint_id)` (ADR-009) → `publish(owner_id, "approval:new", ...)` (rt-websocket). `max_iter_exceeded` via reducer de soma (ADR-005). Worker down → nó `failed` (ADR-001), run pausado, retomável.
- `worker_client.execute(agent_id: str, inputs: dict, capabilities: dict, timeout: int = 120) -> WorkerResponse` (ver rt-worker).
- `checkpoint.py`: `PostgresSaver` configurado (`DATABASE_URL`), `setup()` cria tabelas, save a cada nó, listagem.

**Contrato que consome:** `compile_pipeline` (pe-compiler), `AgentCapabilities`/`loader` (pe-loader), `create_approval_node`/`service` (hitl-approval), `publish`/`ConnectionManager` (rt-websocket), model `PipelineRun`/`Checkpoint` (db-models), worker (NGINX :8081).

**Critérios de aceite testáveis:** (a) A→B→C executa emitindo `pipeline:status`; (b) execute sobre pipeline running → 409; (c) PUT durante run → 409 `graph_running`; (d) nó de aprovação pausa, resume retoma, roteia por decision; (e) worker down → nó failed, run retomável; (f) maxIterations baixo aborta loop (status failed); (g) upsert de ApprovalRequest idempotente (re-run não duplica); (h) stop cancela aprovações pendentes.

**Testes obrigatórios:** `tests/test_executor.py` (execute/pause/resume/stop, 409s), `tests/test_worker_client.py` (retry/backoff/timeout, worker mock), `tests/test_checkpoint.py` (save/load round-trip, banco de teste isolado), `tests/test_max_iter.py` (aborto de loop). Banco de teste isolado + LangGraph `PostgresSaver` no banco de teste.

---

## 2.18 rt-worker

**Objetivo:** container stateless `agent-worker` que executa **um** agente por request, baixa `.yml`/`.md` do MinIO, retorna output+action+logs. Fase 6.

**Arquivos que cria:** `agent-worker/app/{main.py,worker.py,minio_client.py,loader.py}`.

**Contrato que expõe (HTTP interno, via NGINX :8081):**
- `POST /execute` → body `{ agentId, nodeId, inputs, timeout }` (o capabilities é **derivado aqui**, ADR-008 — o orchestrator passa só agentId+inputs+timeout; **decisão coerente**: `rt-worker` baixa o `.yml`, resolve capabilities localmente). Header `X-Worker-Token`.
  - 200 `{ status:"completed"|"failed", outputs, action:"follow"|"return"|"finalize", iterations:int, logs:[str] }`.
  - 401 `{ error:"unauthorized", code:"worker_token_invalid" }`.
  - 404 `{ error:"agent_not_found", code:"agent_not_found" }`.
  - 408/429/502 estruturados (sem stack trace).
- `GET /health` → 200.

**Contrato de execução (worker own):** `worker.py`: (1) `minio_client.download_agent(agent_id) -> AgentSnapshot` (parse .yml); (2) resolver capabilities (`worker.loader.load(snapshot)` — **worker own loader**, análogo ao orchestrator mas minimalista; ADR-008); (3) instanciar `Agent`; (4) `Agent.run(inputs, capabilities)`; (5) `{ outputs, action, logs }`. Nunca propaga exceção (ADR-001): erro → `{ status:"failed", error }` como state update.

**MinIO:** `minio_client.download_agent(agent_id) -> dict`, `download_skills(skill_ids) -> list[str]` (conteúdo `.md`). Cache local por versão + TTL 5min (mitigar latência, D6).

**Critérios de aceite testáveis:** (a) POST /execute com agentId válido → output + action; (b) agentId inexistente → 404; (c) sem/erro `X-Worker-Token` → 401; (d) MinIO em falta → 502 estruturado; (e) GET /health → 200.

**Testes obrigatórios:** `tests/test_worker_execute.py` (mock minio, mock LLM), `tests/test_worker_auth.py` (X-Worker-Token), `tests/test_worker_minio.py` (round-trip download). Banco de teste **não** precisa (worker é stateless, sem DB).

---

## 2.19 rt-websocket

**Objetivo:** conexão única `wss(s)://<host>/api/ws?token=<JWT>`, ConnectionManager por owner, `publish(owner_id, channel, data)`, 5 canais spec §9.7. Fase 6.

**Arquivos que cria:** `agent-orchestrator/app/runtime/websocket.py`, `app/api/ws.py`.

**Contrato que expõe:**
- `ConnectionManager`: set de conexões por `owner_id`; handshake valida JWT (consome `auth-backend`); token inválido → close código **policy violation**.
- `publish(owner_id: str, channel: str, data: dict)`: manda `{ "channel": channel, "data": data }` a todas as conexões daquele owner (filtra ownerId; o cliente filtra pipelineId). Interface consumida por `rt-executor` e `hitl-approval`.
- `app/api/ws.py`: router FastAPI WebSocket em `/api/ws` (o NGINX faz upgrade → orchestrator:8000).

**Canais (payload, spec §9.7):**
- `pipeline:status` → `{ pipelineId, runId, nodeId, status, at }`.
- `pipeline:log` → `{ pipelineId, runId, nodeId, level, message, at }`.
- `agent:output` → `{ pipelineId, runId, nodeId, output }`.
- `approval:new` → `{ approvalId, pipelineId, runId, nodeId, message, at }`.
- `approval:resolved` → `{ approvalId, pipelineId, runId, nodeId, decision, at }`.

**Contrato que consome:** validação JWT (`auth-backend`), `get_current_user` (ownerId do JWT), `POST /execute` via NGINX (infra-nginx :8081).

**Critérios de aceite testáveis:** (a) handshake sem token → close policy violation; (b) `publish("owner", "pipeline:status", payload)` → cliente recebe frame `{channel,data}`; (c) owner A não recebe evento de owner B (filtro); (d) reconexão refaz REST (`/api/pipelines/{id}`) para sincronizar.

**Testes obrigatórios:** `tests/test_websocket.py` (handshake auth, publish por owner, filtro, reconexão). Banco de teste **não** precisa (websocket manager é em memória).

---

## 2.20 hitl-approval

**Objetivo:** função do nó de aprovação (`interrupt()` + upsert ApprovalRequest pós-interrupt + rotear via `Command`), serviço de ApprovalRequest (upsert idempotente), API de aprovações. Fase 7. Consome `pe-compiler` (insere o nó), `rt-websocket` (`publish`), `rt-executor` (hook de interrupção, `thread_id`).

**Arquivos que cria:** `agent-orchestrator/app/approvals/{node_function.py,service.py}, app/api/approvals.py`. **Não** cria `resume.py` aqui (é do `hitl-resume`).

**Contrato de função do nó (exporta ao compiler):**
- `create_approval_node(edge_config: EdgeConfig) -> Callable[[State], Coroutine]` (node_function.py). Primeira execução: monta payload (output do source, contexto, canal, mensagem), `interrupt(payload)` (LangGraph pausa). Retomada: `interrupt()` retorna a resposta → **upsert** `ApprovalRequest` chave `(pipeline_id, node_id, checkpoint_id)` (ADR-009) → notifica (`approval:new`) → `Command(goto="proceed"` ou `"reject_handler"`, ADR-006; `reject_handler` = source, ou END se condition==action==return).
- Só montaje de payload **antes** do `interrupt()` (sem side effects). Persistência + notificação **pós-interrupt**.

**Contrato de serviço (service.py):** `upsert_approval(pipeline_id, node_id, checkpoint_id, payload) -> ApprovalRequest` (upsert; se já `pending`, não recria), `list_approvals(status?, pipeline_id?, page?)`, `respond(approval_id, decision, response?) -> ApprovalRequest`, `cancel_pending(approval_id)`. Multi-interrupt: aceita `{ interruptId: response }`.

**Contrato que expõe (rotas, prefixo `/api`):**
- `GET /api/approvals?status=pending|resolved|cancelled&pipelineId=&page=` → paginado.
- `POST /api/approvals/{id}/respond` → body `{ decision:"approved"|"rejected"|"revised", response? }` → 200 `ApprovalRequest` / 409 `already_responded` / 404.
- `DELETE /api/approvals/{id}` → 204 / 404 (cancela pendente).

**Contrato que consome:** model `ApprovalRequest` (db-models), `publish` (rt-websocket), `thread_id`/checkpoint (rt-executor), `create_approval_node` (exportado por ele mesmo; o compiler o importa), `graph.invoke`/`thread_id` (rt-executor).

**Critérios de aceite testáveis:** (a) edge `requiresApproval:true` pausa no nó (interrupt); (b) resposta `approved` → `Command(goto=target)` retoma; (c) `rejected` → `Command(goto=source|END)`; (d) re-execução do não duplica ApprovalRequest (upsert por chave); (e) `approval:new` chega via WebSocket após persistência; (f) multi-interrupt (fan-out) retoma com mapa `{interruptId: response}`; (g) stop cancela pendentes (409 `already_responded` ao responder já respondida).

**Testes obrigatórios:** `tests/test_approval_node.py` (interrupt pausa, resume roteia), `tests/test_approval_service.py` (upsert idempotente, respond, cancel), `tests/test_approval_ws.py` (approval:new/resolved emitidos). Banco de teste isolado.

---

## 2.21 hitl-notification

**Objetivo:** interface de notificação + canal in-app (WebSocket, V1), email (SMTP, desligado por padrão), stubs Teams/Slack (V2). O `publish` (WebSocket) é de `rt-websocket`; este nó **orquestra** a entrega multi-canal e decide o fallback. Fase 7. Consome `rt-websocket` (`publish`), `db-models` (`ApprovalRequest`).

**Arquivos que cria:** `agent-orchestrator/app/notifications/{interface.py, inapp.py, email.py, teams.py, slack.py}`.

**Contrato que expõe (interface consumida por hitl-approval):**
- `NotificationChannel = Literal["in-app", "email", "teams", "slack"]` (declarado, resolve divergência C-01 do contrato §11.7).
- `async notify(approval: ApprovalRequest, channel: NotificationChannel) -> None`: dispara o canal. in-app = `publish(owner_id, "approval:new", payload)` (rt-websocket). email = template SMTP (só se `ENABLE_EMAIL_NOTIFICATIONS=true` e `SMTP_*` presentes; caso contrário, log e ignora, nunca quebra o fluxo). teams/slack = stubs que logam `not implemented` (V2).
- `async notify_with_fallback(approval, primary, response_url?)`: tenta `primary`; se falhar, tenta `fallback_channel` até `max_retries` (ADR-007 de resiliência do D7). Nunca propaga exceção para o nó de aprovação (o canal falho não trava a pipeline; o timeout global do D6 é a rede de segurança).

**Contrato que consome:** `publish(owner_id, channel, data)` (rt-websocket), `settings.smtp_*` + `ENABLE_EMAIL_NOTIFICATIONS` (infra-docker), model `ApprovalRequest` (db-models).

**Critérios de aceite testáveis:** (a) in-app emite `approval:new` via `publish`; (b) email não é enviado quando `ENABLE_EMAIL_NOTIFICATIONS=false` (desligado por padrão); (c) canal principal simulado como falho → fallback é tentado; (d) todos os canais falham → exceção não escapa para o nó (log + continue).

**Testes obrigatórios:** `tests/test_notify_inapp.py` (publish chamado), `tests/test_notify_email_disabled.py` (não envia sem flag), `tests/test_notify_fallback.py` (fallback). Banco de teste não precisa (notificação é em memória/HTTP).

---

## 2.22 hitl-resume

**Objetivo:** retomar a execução após a resposta humana: lê a `ApprovalRequest`, constrói o `Command(resume=...)` (mapa em multi-interrupt) e chama `graph.invoke(Command(resume=...), config)` com o `thread_id` correto. Fase 7. Consome `rt-executor` (`compile_pipeline` + `thread_id` + graph), `db-models` (`ApprovalRequest`), `hitl-approval` (`service.respond`).

**Arquivos que cria:** `agent-orchestrator/app/approvals/resume.py`.

**Contrato que expõe (assinatura):**
- `async resume(approval_id: str, response: dict) -> PipelineRun`: (1) busca a `ApprovalRequest` (404 se inexistente); (2) valida a decisão; (3) constrói `Command(resume=<valor>)` — em single-interrupt, o valor é a resposta direta; em multi-interrupt, um mapa `{interruptId: response}`; (4) `graph.invoke(Command(resume=...), config={thread_id})` (rt-executor expõe o graph compilado + thread_id); (5) atualiza `ApprovalRequest.status` via `hitl-approval.service`.
- **Idempotência (ADR-009):** o resume consome a `ApprovalRequest` já criada pelo upsert pós-interrupt (executor/hitl-approval); não recria. A resposta humana alimenta o `interrupt()` que já está congelado no checkpoint.

**Contrato que consome:** `compile_pipeline` + `thread_id` (rt-executor), `ApprovalRequest` (db-models), `service.respond` (hitl-approval), `create_approval_node` (hitl-approval, para reconstituir a topologia com o nó de aprovação).

**Critérios de aceite testáveis:** (a) resposta `approved` retoma e segue para o target; (b) `rejected` devolve ao source ou encerra; (c) multi-interrupt retoma só quando todas as respostas chegam (mapa); (d) responder duas vezes → 409 `already_responded`.

**Testes obrigatórios:** `tests/test_resume.py` (approved/rejected, single + multi-interrupt, duplicata). Banco de teste isolado + LangGraph `PostgresSaver` no banco de teste.

---

# 3. Tabela de endpoints

> Derivada da spec §9 + contrato §8 (envelope, camelCase, autenticação opt-out). Prefixo `/api` implícito (o `infra-docker` cria `APIRouter(prefix="/api")` em `main.py`; cada router declara suas rotas sem o `/api` no início). `ownerId` vem do `sub` do JWT (V1 single-user = admin do seed). **Nenhum** endpoint é público exceto `GET /api/health`, `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me` (opt-out do `get_current_user`).

| # | Método | Rota | Nó | Auth | Sucesso | Códigos de erro |
|---|--------|------|-----|------|---------|-----------------|
| 1 | GET | `/health` | infra-docker | nenhuma | 200 `{status:"ok"}` | — |
| 2 | GET | `/api/health` | infra-docker | nenhuma | 200 `{status:"ok"}` | — |
| 3 | POST | `/api/auth/login` | auth-backend | nenhuma | 200 `{accessToken, refreshToken}` | 401 `not_authenticated`, 429 `rate_limited` |
| 4 | POST | `/api/auth/refresh` | auth-backend | nenhuma | 200 `{accessToken}` | 401 `not_authenticated`, 429 `rate_limited` |
| 5 | GET | `/api/auth/me` | auth-backend | access JWT | 200 `{userId, email, name}` | 401 `not_authenticated` |
| 6 | POST | `/api/agents` | be-agents | access JWT | 201 `Agent` | 400 `invalid_graph`, 422 `schema_validation` |
| 7 | GET | `/api/agents?page=&limit=&type=` | be-agents | access JWT | 200 `{items,total,page,limit}` | 429 `rate_limited` |
| 8 | GET | `/api/agents/{id}` | be-agents | access JWT | 200 `Agent` | 404 `agent_not_found` |
| 9 | PUT | `/api/agents/{id}` | be-agents | access JWT | 200 `Agent` | 400 `invalid_graph`, 404 `agent_not_found`, 409 `graph_running` |
| 10 | DELETE | `/api/agents/{id}` | be-agents | access JWT | 204 | 404 `agent_not_found`, 409 `graph_running` |
| 11 | POST | `/api/agents/chat` | be-agents | access JWT | 200 SSE stream | 429 `rate_limited` |
| 12 | POST | `/api/agents/{id}/chat` | be-agents | access JWT | 200 SSE stream | 404 `agent_not_found`, 429 `rate_limited` |
| 13 | GET | `/api/skills` | be-skills | access JWT | 200 `{items,total,page,limit}` | — |
| 14 | POST | `/api/skills` | be-skills | access JWT | 201 `Skill` | 400 `schema_validation` |
| 15 | GET | `/api/skills/{id}` | be-skills | access JWT | 200 `Skill` | 404 `skill_not_found` |
| 16 | PUT | `/api/skills/{id}` | be-skills | access JWT | 200 `Skill` | 404 `skill_not_found` |
| 17 | DELETE | `/api/skills/{id}` | be-skills | access JWT | 204 | 404 `skill_not_found` |
| 18 | GET | `/api/tools` | be-skills | access JWT | 200 `{items,total,page,limit}` | — |
| 19 | POST | `/api/tools` | be-skills | access JWT | 201 `CustomTool` | 400 `schema_validation` |
| 20 | GET | `/api/tools/{id}` | be-skills | access JWT | 200 `CustomTool` | 404 `tool_not_found` |
| 21 | PUT | `/api/tools/{id}` | be-skills | access JWT | 200 `CustomTool` | 404 `tool_not_found` |
| 22 | DELETE | `/api/tools/{id}` | be-skills | access JWT | 204 | 404 `tool_not_found` |
| 23 | POST | `/api/tools/{id}/deploy` | be-skills | access JWT | 200 `CustomTool` | 400 `schema_validation`, 404 `tool_not_found` |
| 24 | POST | `/api/tools/{id}/test` | be-skills | access JWT | 200 `{result}` | 400 `schema_validation`, 404 `tool_not_found` |
| 25 | GET | `/api/mcp-servers` | be-skills | access JWT | 200 `{items,total,page,limit}` | — |
| 26 | POST | `/api/mcp-servers` | be-skills | access JWT | 201 `MCPServer` | 400 `schema_validation` |
| 27 | GET | `/api/mcp-servers/{id}` | be-skills | access JWT | 200 `MCPServer` | 404 `mcp_server_not_found` |
| 28 | PUT | `/api/mcp-servers/{id}` | be-skills | access JWT | 200 `MCPServer` | 404 `mcp_server_not_found` |
| 29 | DELETE | `/api/mcp-servers/{id}` | be-skills | access JWT | 204 | 404 `mcp_server_not_found` |
| 30 | POST | `/api/mcp-servers/{id}/test` | be-skills | access JWT | 200 `{discoveredTools}` | 404 `mcp_server_not_found`, 409 `connection_error` |
| 31 | POST | `/api/knowledge` | be-knowledge | access JWT | 201 `KnowledgeBase` | 400 `schema_validation` |
| 32 | GET | `/api/knowledge?scope=&source=` | be-knowledge | access JWT | 200 `{items,total,page,limit}` | — |
| 33 | GET | `/api/knowledge/{id}` | be-knowledge | access JWT | 200 `KnowledgeBase` | 404 `knowledge_base_not_found` |
| 34 | PUT | `/api/knowledge/{id}` | be-knowledge | access JWT | 200 `KnowledgeBase` | 404 `knowledge_base_not_found` |
| 35 | DELETE | `/api/knowledge/{id}` | be-knowledge | access JWT | 204 | 404 `knowledge_base_not_found` |
| 36 | POST | `/api/knowledge/{id}/upload` | be-knowledge | access JWT | 200 `{documentId}` | 400 `schema_validation`, 404 `knowledge_base_not_found`, 429 `rate_limited` |
| 37 | GET | `/api/knowledge/{id}/documents` | be-knowledge | access JWT | 200 `{items,total,page,limit}` | 404 `knowledge_base_not_found` |
| 38 | DELETE | `/api/knowledge/{id}/documents/{docId}` | be-knowledge | access JWT | 204 | 404 `knowledge_base_not_found`, 404 `document_not_found` |
| 39 | POST | `/api/knowledge/query` | be-knowledge | access JWT | 200 `{chunks:[{score,content}]}` | 400 `schema_validation` |
| 40 | POST | `/api/pipelines` | rt-executor | access JWT | 201 `Pipeline` | 400 `invalid_graph`, 422 `schema_validation` |
| 41 | GET | `/api/pipelines?page=&limit=&status=` | rt-executor | access JWT | 200 `{items,total,page,limit}` | — |
| 42 | GET | `/api/pipelines/{id}` | rt-executor | access JWT | 200 `Pipeline` | 404 `pipeline_not_found` |
| 43 | PUT | `/api/pipelines/{id}` | rt-executor | access JWT | 200 `Pipeline` | 400 `invalid_graph`, 404 `pipeline_not_found`, 409 `graph_running` |
| 44 | POST | `/api/pipelines/validate` | rt-executor (consome pe-validator) | access JWT | 200 `{valid:bool, errors:[...]}` | 400 `invalid_graph`, 422 `schema_validation` |
| 45 | POST | `/api/pipelines/{id}/execute` | rt-executor | access JWT | 200 `PipelineRun` | 404 `pipeline_not_found`, 409 `pipeline_already_running` |
| 46 | POST | `/api/pipelines/{id}/pause` | rt-executor | access JWT | 200 `PipelineRun` | 404 `pipeline_not_found`, 409 `pipeline_not_running` |
| 47 | POST | `/api/pipelines/{id}/resume` | rt-executor (hitl-resume) | access JWT | 200 `PipelineRun` | 404 `pipeline_not_found`, 409 `pipeline_not_running` |
| 48 | POST | `/api/pipelines/{id}/stop` | rt-executor | access JWT | 200 `PipelineRun` | 404 `pipeline_not_found`, 409 `pipeline_not_running` |
| 49 | GET | `/api/pipelines/{id}/runs?page=&limit=` | rt-executor | access JWT | 200 `{items,total,page,limit}` | 404 `pipeline_not_found` |
| 50 | GET | `/api/pipelines/{id}/checkpoints?page=&limit=` | rt-executor | access JWT | 200 `{items,total,page,limit}` | 404 `pipeline_not_found` |
| 51 | POST | `/api/pipelines/{id}/checkpoints/{cpId}/resume` | rt-executor | access JWT | 200 `PipelineRun` | 404 `pipeline_not_found`, 404 `checkpoint_not_found` |
| 52 | GET | `/api/artifacts/{id}` | rt-executor | access JWT | 200 `Artifact` (content) | 404 `artifact_not_found` |
| 53 | GET | `/api/approvals?status=&pipelineId=&page=` | hitl-approval | access JWT | 200 `{items,total,page,limit}` | 429 `rate_limited` |
| 54 | POST | `/api/approvals/{id}/respond` | hitl-approval | access JWT | 200 `ApprovalRequest` | 404 `approval_not_found`, 409 `already_responded` |
| 55 | DELETE | `/api/approvals/{id}` | hitl-approval | access JWT | 204 | 404 `approval_not_found`, 409 `already_responded` |
| 56 | GET | `/api/integrations` | be-integrations | access JWT | 200 `{items,total,page,limit}` | — |
| 57 | POST | `/api/integrations` | be-integrations | access JWT | 201 `Integration` | 400 `schema_validation` |
| 58 | GET | `/api/integrations/{id}` | be-integrations | access JWT | 200 `Integration` | 404 `integration_not_found` |
| 59 | PUT | `/api/integrations/{id}` | be-integrations | access JWT | 200 `Integration` | 404 `integration_not_found` |
| 60 | DELETE | `/api/integrations/{id}` | be-integrations | access JWT | 204 | 404 `integration_not_found` |
| 61 | GET | `/api/integrations/github/repos` | be-integrations | access JWT | 200 `{repos}` | 404 `integration_not_found`, 502 `github_error` |
| 62 | GET | `/api/integrations/github/repos/{owner}/{repo}/pulls?state=` | be-integrations | access JWT | 200 `{pulls}` | 404 `integration_not_found`, 502 `github_error` |
| 63 | GET | `/api/integrations/github/repos/{owner}/{repo}/issues?state=&labels=` | be-integrations | access JWT | 200 `{issues}` | 404 `integration_not_found`, 502 `github_error` |
| 64 | GET | `/api/integrations/rivvn/authorize` | be-integrations | access JWT | 307 redirect | 403 `rivvn_contract_inactive` |
| 65 | GET | `/api/integrations/rivvn/callback` | be-integrations | access JWT | 200 `{status}` | 400 `invalid_code`, 403 `rivvn_contract_inactive` |
| 66 | GET | `/api/integrations/rivvn/status` | be-integrations | access JWT | 200 `{connected, contractStatus}` | 403 `rivvn_contract_inactive` |
| 67 | DELETE | `/api/integrations/rivvn` | be-integrations | access JWT | 204 | 404 `integration_not_found` |
| 68 | GET | `/api/ws` (WebSocket upgrade) | rt-websocket | JWT no query string | 101 upgrade | close `policy_violation` (token inválido) |

**Notas da tabela:**
- **CamelCase:** `owner_id` → `ownerId`, `source_output` → `sourceOutput`, `requires_approval` → `requiresApproval`, `contract_status` → `contractStatus` (contrato §8).
- **Envelope de erro:** `{ "error": str, "code": str, "details"?: object }` (contrato §8). Ex.: 400 `invalid_graph` → `details.errors = [{rule, message, nodeId?, edgeId?}]`.
- **Pagination:** `{ "items": [...], "total": int, "page": int, "limit": int }` (contrato §8).
- **Auth opt-out:** só `/api/health`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/me` são públicos. Todo router novo **nasce protegido** por `get_current_user` (dependência global com lista de exceções — `auth-backend` testa isso, §2.8).
- **`/api/ws`:** upgrade WebSocket (NGINX faz `Upgrade`/`Connection` → orchestrator:8000, contrato §2.2 regra 3). Token JWT na query string; close `policy_violation` se inválido.
- **Rivvn:** 403/404 com `code` claro; UI desabilitada na V1 (contrato §10).

---

# 4. Riscos por fase e checklist do revisor

> Cada fase tem um revisor (contrato §13). Aqui: risco principal + o que checar com rigor. Os revisores validam o handoff entre nós da mesma fase (mesma fase = mesmo revisor, sem sobreposição de arquivos).

## FASE 1 — Infra (revisor: infra-review)

**Risco:** scaffold quebra a descoberta de routers; healthchecks falsos; `.env` com driver errado; worker exposto na :80.

**Checklist rigoroso:**
- [ ] `main.py` inclui **automaticamente** todo módulo em `app/api/` com `router = APIRouter(...)` via `importlib` (provar com um router de prova, depois remover).
- [ ] `APIRouter(prefix="/api")` central em `main.py`; routers filhos declaram rotas **sem** `/api` no início (provar `/api/health`, `/api/probe`).
- [ ] `DATABASE_URL` usa `asyncpg` (não `psycopg`), conforme §3.
- [ ] Healthchecks reais: orchestrator `/health` 200, worker `/health` 200, minio via `mc`/`curl`, postgres `pg_isready`.
- [ ] `depends_on` com `condition: service_healthy` (orchestrator ← postgres+minio; nginx ← todos).
- [ ] Worker **não** tem porta publicada nem rota na :80; orchestrator→worker só por server block interno NGINX :8081 com `X-Worker-Token`.
- [ ] `.env.example` completo (contrato §2.4); `JWT_SECRET`/`NEXTAUTH_SECRET` = mesmo valor.
- [ ] Entrypoint roda `alembic upgrade head` + seed antes do `uvicorn`, tolerando tabelas inexistentes.
- [ ] `.gitattributes` com `*.sh`/Dockerfiles/compose em `eol=lf`.
- [ ] `spike` confirma instalabilidade dos pacotes pinados + superfície LangGraph (pendência §13).

## FASE 2 — DB (revisor: db-review)

**Risco:** schema incompleto; pgvector sem dimensão fixa; migration diverge dos models; fixture de teste usa o banco de dev.

**Checklist rigoroso:**
- [ ] `create_all` gera **todas** as tabelas da spec §4 (incluindo `knowledge_chunk.embedding vector(1536)`).
- [ ] Migration `0001_initial.py` reflete os models (comparar `MetaData`); `alembic upgrade head` limpo.
- [ ] Banco de teste isolado: fixture cria `agent_portal_test_<uuid>`, destrói no teardown; **nunca** o banco `agent_portal`.
- [ ] Usuário `agent_portal` tem permissão de criar bancos (para o fixture).
- [ ] `seed.py` cria **só** o admin (0 se env em falta; idempotente; nunca agente/skill/tool/pipeline — contrato §0).
- [ ] `owner_id` do admin documentado como `sub==owner_id` (V1 single-user).

## FASE 3 — Auth (revisor: auth-review)

**Risco:** JWT reutilizável; auth vaza para o worker; router novo nasce desprotegido.

**Checklist rigoroso:**
- [ ] `get_current_user` protege **opt-out**; router novo (criado por outro nó) **nasce protegido** (testar).
- [ ] Refresh token **não** devolve o mesmo refresh reutilizável indefinidamente (blacklist `jti` em memória ou rotaciona; testar reuso → 401).
- [ ] Access 15 min / refresh 7 dias; `typ` distinto `access`/`refresh`.
- [ ] Login com credencial errada → 401 genérico (não revela se e-mail existe); rate limit 429 envelope.
- [ ] Hash bcrypt custo 12 (`app/core/security.py`, dono infra-docker).
- [ ] Fluxo NextAuth: `authorize()` chama `POST <ORCHESTRATOR_API_URL>/api/auth/login` (URL interna, não localhost); token por `GET /api/session-token` (nunca localStorage).
- [ ] Validação JWT reutilizável para o WebSocket handshake.

## FASE 4 — Backend CRUD (revisor: be-review)

**Risco:** MinIO+Postgres inconsistentes; contrato de agente inválido aceito; Rivvn sem gate; dono de `app/api/integrations.py` ambíguo.

**Checklist rigoroso:**
- [ ] CRUD agente/skill: transação compensatória MinIO↔Postgres (MinIO falha → rollback Postgres).
- [ ] Validação de contrato (inputs/outputs/actions) → 400 `invalid_graph` com `details.errors`.
- [ ] `shell` opt-in (`shellAccess`); sandbox isola (subprocesso, timeout 30s, sem secrets).
- [ ] Rivvn: `403`/`404` sem `contractStatus=active` (gate comercial, contrato §10).
- [ ] `app/api/integrations.py` é **só** do `be-integrations` (handoff be-knowledge→be-integrations documentado; be-knowledge entrega `knowledge/rivvn/*`).
- [ ] `be-skills` **não** cria `app/skills/loader.py` (é do `pe-loader`, FASE 5).
- [ ] Listagens paginadas (`?page=&limit=`); envelope camelCase.

## FASE 5 — Pipeline engine (revisor: pe-review)

**Risco:** State dinâmico quebra checkpoint; regra 7 mal aplicada; dono de `app/api/pipelines.py` duplicado; loader em lugar errado (ADR-008).

**Checklist rigoroso:**
- [ ] `State` é **fixo** (ADR-002); namespace por nodeId é convenção de valor (ADR-003). Nunca `types.new_class()`.
- [ ] Validador: 11 regras testadas (uma por regra); regra 7 = injera flow incondicional (não erro); regra 10 = aviso (não erro).
- [ ] `pe-validator` **não** cria arquivo em `app/api/` (contrato §9); validação vive em `app/api/pipelines.py` do `rt-executor`.
- [ ] `compile_pipeline` gera StateGraph com nós de aprovação (`approval_node_{edgeId}`) + arestas proceed/reject (ADR-006).
- [ ] `AgentCapabilities` vive em `app/compiler/state.py` (pe-compiler); `pe-loader` só o consome.
- [ ] **Tensão ADR-008 vs §9:** o contrato §9 atribui `app/skills/loader.py` ao `pe-loader` (orchestrator); ADR-008 diz "loader no worker". Decisão deste plano: o **loader que o orchestrator monta para expor ao portal/validar** é do `pe-loader`; o **worker tem seu próprio loader minimalista** (ADR-008, executa o agente). Documentar handoff. Revisor confirmar que nenhum dos dois injeta capabilities no snapshot persistido (ADR-008: capacidades derivadas, não persistidas).
- [ ] `route_fn`: maxIterations → conditions → follow (ADR-005/ADR-007). Compiler **não** enforce maxIterations.

## FASE 6 — Runtime (revisor: rt-review)

**Risco:** worker exception aborta o grafo; checkpoint não round-tripa; 409s ausentes; worker down não retry.

**Checklist rigoroso:**
- [ ] **ADR-001:** node function **nunca** propaga exceção do worker; erro → `{status:"failed",error}`; grafo não aborta. Testar: worker fora do ar → nó `failed`, run retomável.
- [ ] `worker_client.execute(agent_id, inputs, timeout)` — **não** passa `capabilities` no body (ADR-008: worker deriva). Retry 3x backoff 2/4/8s.
- [ ] `thread_id = f"{pipelineId}:{runId}"` (spec §4.3).
- [ ] 409s: execute sobre running → `pipeline_already_running`; PUT durante run → `graph_running`.
- [ ] PostgresSaver round-tripa o State fixo (save→load→resume). Testar no banco de teste.
- [ ] maxIterations via reducer de soma `Annotated[dict, operator.add]` (ADR-005); node function checa no início (ADR-007).
- [ ] WebSocket: handshake valida JWT (close `policy_violation`); `publish` filtra por ownerId; 5 canais spec §9.7.

## FASE 7 — HITL (revisor: hitl-review)

**Risco:** duplicata de ApprovalRequest em resume; notificação antes do interrupt; dono do nó de aprovação ambíguo.

**Checklist rigoroso:**
- [ ] **ADR-009:** ApprovalRequest criada pelo **executor** ao detectar interrupção, upsert por chave `(runId, nodeId, interruptId)`; re-execução não duplica. (Nota: o contrato §11.1 cita a chave como `(pipeline_id, node_id, checkpoint_id)`; este plano usa `interruptId` — revisor unificar o nome da chave entre executor e serviço.)
- [ ] Notificação **só após** upsert (ADR-009); persistência + notificação pós-interrupt.
- [ ] Nó de aprovação: compiler gera topologia (pe-compiler), hitl-approval entrega a função (não há duplicata de dono).
- [ ] Multi-interrupt: retoma com mapa `{interruptId: response}`; stop cancela pendentes.
- [ ] `hitl-notification`: canal principal falha → fallback; nunca propaga exceção para o nó.
- [ ] `hitl-resume`: lê ApprovalRequest, constrói `Command(resume=...)`, `graph.invoke` com thread_id correto.
- [ ] `NotificationChannel` declarado (ADR-001 de C-01): `in-app|email|teams|slack`; V1 só in-app + email.

## FASE 8 — Portal (revisor: fe-review) — fora do escopo deste plano

> Este plano (backend) **não** planeja frontend. O handoff para o agente frontend está na tabela da seção 3 (rotas + payloads) e em `GUIA-API-FRONTEND.md` (a gerar pelo hitl-review, contrato §13).

---

# 5. Furos no contrato

> Contradições/furos encontrados entre contrato, spec, domínios e este plano. Cada entrada: o que conflita, a decisão mínima coerente, e quem aplica. **Nenhum** furo foi contornado na implementação; todos são decididos aqui por precedência (contrato > spec > domínios > este plano) ou documentados para o revisor.

### F1 — Driver do banco no `.env.example` vs §3
- **Furo:** o `.env.example` (§2.4) mostra `postgresql+psycopg://`; a §3 lista `asyncpg` **e** `psycopg[binary]`; o §6 decide "SQLAlchemy 2 async + asyncpg".
- **Decisão:** `DATABASE_URL` usa **asyncpg** (`postgresql+asyncpg://agent_portal:agent_portal@postgres:5432/agent_portal`). `psycopg[binary]` fica como dependência (não usada na V1 async). `.env.example` mantido; driver corrigido para asyncpg. Aplicado no bloco `infra-docker` (dono do `.env.example`).

### F2 — Dimensão de embedding / provider local
- **Furo:** o `.env.example` lista `EMBEDDING_DIM=1536` mas não tem var para provider de embedding local; a spec §7.2 cita fallback local (V2).
- **Decisão:** V1 só OpenAI (ou `mock`) para embeddings; **nenhuma** var de embedding local planejada. `EMBEDDING_PROVIDER=mock` sustenta testes; com chave real, entra OpenAI. Nenhum furo bloqueante — registrado para não inventar feature.

### F3 — Dono de `app/api/integrations.py` (listado em dois domínios)
- **Furo:** a §9 do contrato lista `app/api/integrations.py` em **dois** domínios: D9 (`be-knowledge`, para o gateway Rivvn) e D8 (`be-integrations`).
- **Decisão:** pela convenção "único dono" e pela §9 (`be-integrations` = `app/api/integrations.py`), **`app/api/integrations.py` é do `be-integrations`**. O `be-knowledge` **não** o cria; entrega `knowledge/rivvn/oauth.py` + `client.py` e consome as rotas via client interno. Handoff be-knowledge→be-integrations documentado nos blocos 2.11 e 2.12.

### F4 — Dono de `app/api/pipelines.py` e endpoint de validação
- **Furo:** a §9 do contrato atribui `app/api/pipelines.py` ao `rt-executor`, mas o mesmo §9 diz que `pe-validator` **não** cria arquivo em `app/api/`. Onde vive o endpoint de validação de grafo?
- **Decisão:** `rt-executor` **é** o dono de `app/api/pipelines.py`; nele vivem CRUD **e** validação (`POST /api/pipelines/validate`, que consome `pe-validator.validate_graph`). O `pe-validator` entrega só a função (não cria arquivo em `app/api/`). Resolvido no bloco 2.17 (corrigido em relação à versão anterior deste plano, que invertera o dono).

### F5 — Loader: orchestrator (§9) vs worker (ADR-008)
- **Furo:** a §9 atribui `app/skills/loader.py` ao `pe-loader` (orchestrator); a ADR-008 diz "loader roda no worker". Dois loaders?
- **Decisão:** **dois** loaders, papéis distintos: (a) `pe-loader` (orchestrator) monta o `AgentCapabilities` para **validação/exposição ao portal** e consome o schema fixo de `app/compiler/state.py`; (b) o **worker tem seu próprio loader minimalista** (`agent-worker/app/loader.py`, ADR-008) que baixa `.yml`/`.md` do MinIO e executa o agente. Capacidades são **derivadas em runtime**, nunca persistidas no snapshot (ADR-008/X-01). Nenhum dos dois injeta capabilities no snapshot persistido. Handoff documentado nos blocos 2.15 e 2.18.

### F6 — Chave de idempotência do upsert (nomenclatura)
- **Furo:** o contrato §11.1 cita a chave do upsert como `(pipeline_id, node_id, checkpoint_id)`; a spec §5.3 cita `(pipelineId, nodeId, checkpointId)`; o ADR-009 e os blocos de runtime/HITL citam `(runId, nodeId, interruptId)`.
- **Decisão:** a chave de idempotência é **a mesma entidade** (identifica unicamente uma pausa de aprovação), mas os nomes divergem. `checkpoint_id` no modelo `ApprovalRequest` (db-models) corresponde ao `interruptId`/checkpoint do LangGraph. **Recomendação ao revisor hitl-review/unificar:** padronizar o nome do campo em **um** só lugar (recomendo `interrupt_id`, que é o termo do LangGraph) e espelhar nos blocos 2.17 (executor), 2.20 (hitl-approval) e 2.22 (hitl-resume). Não é bloqueante (a semântica é idêntica), mas evita implementação com dois nomes para a mesma chave.

### F7 — Worker expõe `/execute` ou `/workers/execute`?
- **Furo:** o contrato §2.3 diz `POST http://nginx:8081/execute` (o server block interno **remove** o prefixo; worker expõe `POST /execute`); o D6 diz `POST http://nginx:80/workers/execute` (com prefixo `/workers/`).
- **Decisão:** prevalece o **contrato** (§2.3): worker expõe `POST /execute`; o server block interno do NGINX :8081 faz `proxy_pass` removendo qualquer prefixo. O `worker_client` (rt-executor) chama `POST http://nginx:8081/execute`. O D6 (`/workers/execute`) está desalinhado e deve ser corrigido pelo revisor rt-review (handoff D6→contrato).

---

> **Fonte deste plano:** `CONTRATO-TECNICO.md` (§0,1,2,4,5,6,7,8,9,13), spec `2026-09-17-agent-portal-design.md` (§4,5,6,7,8,9,14), domínios D1–D9, `2026-09-21-execution-plan.md`. Escopo: só `agent-orchestrator/` + `agent-worker/`. Nenhum arquivo do portal é planejado aqui (conformidade com contrato §1).