# Contrato Técnico — Agent Portal

> **Nível:** contrato único que prevalece sobre spec, planos e domínios em caso de conflito.
> **Autor:** Arquiteto de Sistema.
> **Leiam esta arquivo antes de `docs/superpowers/specs/2026-09-17-agent-portal-design.md`, dos domínios D1–D10 e dos planos `PLANO-BACKEND.md` / `PLANO-FRONTEND.md` / `DESIGN-SYSTEM.md`.**
> **Branch de trabalho:** `flow/agent-portal-dev` (o único nó que troca de branch).

---

## 0. Premissa de produto (leiam antes de tudo)

O portal **nasce vazio**. Nenhum agente, skill, tool, servidor MCP, knowledge base, integração ou pipeline está pré-carregado. O **único** registro criado no boot é o **usuário admin inicial** (seed, nó `db-seed`). Nenhum nó — nem a infra, nem o scaffold, nem o `main.py` — cria agente/skill/tool/pipeline no boot. Se um scaffold vier com "seed de demonstração" de agente, é desvio de contrato.

O único seed é o usuário admin: `ADMIN_EMAIL` + `ADMIN_PASSWORD` (bcrypt, custo 12).

---

## 1. Layout canônico do repositório

Árvore completa. Os caminhos são **obrigatórios**; nenhum nó usa caminho solto tipo `orchestrator/` ou `portal/` (o correto é `agent-orchestrator/` e `agent-portal/`).

```
.
├── agent-portal/                     # Next.js 14 App Router (portal)
│   ├── app/
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   ├── (dashboard)/
│   │   │   ├── page.tsx                      # Dashboard
│   │   │   ├── agents/new/page.tsx           # Chat de construção
│   │   │   ├── agents/[id]/page.tsx          # Detalhe/edição
│   │   │   ├── pipelines/[id]/page.tsx       # Flow editor
│   │   │   ├── pipelines/[id]/run/page.tsx   # Monitor
│   │   │   ├── approvals/page.tsx
│   │   │   ├── skills/page.tsx
│   │   │   ├── tools/page.tsx
│   │   │   ├── mcp/page.tsx
│   │   │   └── knowledge/page.tsx
│   │   ├── api/
│   │   │   ├── auth/[...nextauth]/route.ts   # NextAuth
│   │   │   └── session-token/route.ts        # JWT de delegação para API/WS
│   │   ├── layout.tsx
│   │   ├── page.tsx                          # placeholder (fe-shell -> cada nó substitui)
│   │   └── globals.css                       # tokens (fe-shell)
│   ├── components/
│   │   ├── layout/        # sidebar, header, notificações
│   │   ├── ui/            # botão, input, select, textarea, toggle, badge, card, tabela, modal, drawer, tabs, toast, empty state, skeleton
│   │   └── <domínio>/     # AgentChat, FlowEditor, ApprovalPanel, PipelineMonitor, etc.
│   ├── lib/
│   │   ├── api.ts            # client fetch com JWT da sessão, envelope de erro
│   │   ├── websocket.ts      # conexão única, frames, reconexão, inscrição
│   │   └── types.ts          # espelha schemas da API
│   ├── types/next-auth.d.ts
│   ├── auth-options.ts
│   ├── middleware.ts
│   ├── package.json
│   ├── package-lock.json     # gerado aqui pelo infra-docker (npm install)
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── vitest.config.ts
│   └── README.md
├── agent-orchestrator/         # FastAPI, pacote Python `app`
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI + descoberta de routers em app/api/ (dono: infra-docker)
│   │   ├── core/               # config, security, errors, llm, embeddings (dono: infra-docker)
│   │   ├── db/                 # models.py, session.py, seed.py
│   │   ├── auth/               # emissão/validação JWT, get_current_user (dono: auth-backend)
│   │   ├── api/                # um router por recurso (registro automático)
│   │   ├── compiler/           # validator.py, state.py, graph_builder.py
│   │   ├── runtime/            # executor.py, checkpoint.py, worker_client.py, websocket.py
│   │   ├── approvals/          # node_function.py, service.py, resume.py
│   │   ├── notifications/      # interface + canal in-app/email/teams/slack
│   │   ├── agents/             # base + built-in + validator + storage
│   │   ├── skills/             # registry + loader
│   │   ├── tools/              # registry, validator, sandbox, builtins
│   │   ├── mcp/                # registry, client, validator
│   │   ├── knowledge/          # rag.py, chunker.py, embedder.py + rivvn/
│   │   └── integrations/       # CRUD + GitHub
│   ├── tests/
│   ├── alembic/                # env.py + versions/ (dono: db-migrations; skeleton pela infra-docker)
│   ├── alembic.ini
│   ├── pyproject.toml          # (dono: infra-docker)
│   └── Dockerfile              # (dono: infra-docker)
├── agent-worker/               # FastAPI, serviço separado (stateless)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── worker.py
│   │   ├── minio_client.py
│   │   └── loader.py           # (conforme ADR: loader roda aqui)
│   ├── tests/
│   ├── pyproject.toml          # (dono: infra-docker)
│   └── Dockerfile              # (dono: infra-docker)
├── nginx/                      # nginx.conf, conf.d/*.conf, README.md (dono: infra-nginx)
├── postgres/                   # init.sql, README.md (dono: infra-postgres)
├── minio/                      # init-buckets.sh, README.md (dono: infra-minio)
├── spike/                      # prova de arquitetura (não é produto)
├── docker-compose.yml          # (dono: infra-docker)
├── docker-compose.override.yml # (dono: infra-docker, dev)
├── .env.example                # (dono: infra-docker)
├── .dockerignore               # (dono: infra-docker)
├── .gitignore                  # (dono: infra-docker)
├── .gitattributes              # (dono: infra-docker, LF para *.sh e Dockerfiles)
└── README.md                   # (opcional, fora do escopo deste contrato)
```

**Regra de descoberta de routers (contrato §3):** `app/main.py` (dono: infra-docker) importa e inclui automaticamente **todo** módulo em `app/api/` que exponha um objeto chamado `router` (via `importlib` + `APIRouter.include_router`). Assim, nós paralelos **só criam o próprio arquivo** em `app/api/<dominio>.py` com `router = APIRouter(...)`. Ninguém edita `main.py` para registrar um router novo. Se um nó precisa de mais de um router no arquivo, tudo bem; se precisar de um arquivo fora de `app/api/`, peça ao dono do `main.py`.

**Donos de arquivos compartilhados (único dono por arquivo, confirmado em §11):**
`docker-compose.yml`, `docker-compose.override.yml`, `.env.example`, `.dockerignore`, `.gitignore`, `.gitattributes`, os Dockerfiles, `agent-orchestrator/app/main.py`, `agent-orchestrator/app/core/*`, `agent-orchestrator/pyproject.toml`, `agent-worker/pyproject.toml`, `agent-portal/package.json`, `agent-portal/package-lock.json`, `agent-portal/tsconfig.json`, `agent-portal/next.config.ts` -> **infra-docker**. `nginx/*` -> **infra-nginx**. `postgres/*` -> **infra-postgres**. `minio/*` -> **infra-minio**. `agent-orchestrator/alembic/` (env.py + versions) -> **db-migrations**. `agent-portal/app/globals.css`, `agent-portal/app/layout.tsx`, `agent-portal/README.md` -> **fe-shell**.

---

## 2. Portas, rotas e variáveis de ambiente

NGINX :80 é o **único** ponto de entrada público. Toda a API FastAPI vive sob `/api` (inclusive `GET /api/health`; o container também expõe `GET /health` para o healthcheck do Docker). O portal fala com a API pela **mesma origem** (sem CORS) porque o NGINX serve ambos.

### 2.1 Tabela de portas (internas / host / pública)

| Serviço | Interna | Host (publicada) | Rota pública | Comentários |
|---|---|---|---|---|
| nginx (público) | :80 | **:80** | `http://localhost/` | único entry point |
| nginx (interno) | :8081 | *(não publicada)* | só de dentro da rede | pool de workers |
| portal (Next.js) | :3000 | *(não publicada)* | via `:80` | |
| orchestrator (FastAPI) | :8000 | *(não publicada)* | via `/api` | |
| agent-worker (FastAPI) | :9000 | *(não publicada)* | via `:8081` | **nunca** acessível pela :80 |
| postgres (pgvector) | :5432 | **:15432** | psql | evita colidir com host |
| minio | :9001 (API) / :9002 (console) | **:19001** / **:19002** | console | volumes persist. |

**Regra:** nenhuma porta interna muda. As publicadas não colidam com o host (Postgres host já usa 5432, então publica-se 15432). O worker **não** tem porta publicada nem rota na :80: o orchestrator o chama por um server block interno do NGINX (§2.3).

### 2.2 Rotas do NGINX e precedência

O `nginx/nginx.conf` (dono: infra-nginx) implementa **esta** tabela, em **esta** ordem de precedência (`location = ` > `location ^~ /api/portal*` > `location /api/` > `location /`):

| Precedência | Locação | Destino | Notas |
|---|---|---|---|
| 1 | `location = /api/auth` , `location /api/auth/` | **portal:3000** | NextAuth (`[...nextauth]`). **Nunca** vai para a API. |
| 2 | `location = /api/session-token` | **portal:3000** | route handler que devolve o JWT de delegação. |
| 3 | `location = /api/ws` (sem `/` final) | **orchestrator:8000** | WebSocket upgrade (`Upgrade`/`Connection`, timeouts longos). |
| 4 | `location /api/` | **orchestrator:8000** | **mantém** o prefixo `/api` (`proxy_pass http://orchestrator:8000/api/`). |
| 5 | `location /` | **portal:3000** | tudo o resto (SPA, `/_next/`, assets, HMR). |

**Nota sobre o WebSocket (decisão do contrato):** o WebSocket único é `/api/ws` (não `/ws` na spec 9.7). O cliente conecta em `wss(s)://<host>/api/ws?token=<JWT>`. O NGINX faz `Upgrade`/`Connection` e proxy para o **orchestrator:8000** (não para o portal): o servidor WebSocket vive no orchestrator (`app/api/ws.py`, rt-websocket). A regra 3 acima já aponta para `orchestrator:8000`; a precedência `location = /api/ws` sobre `location /api/` evita ambiguidade com qualquer route handler do portal (não há nenhum usando `/api/ws`).

Nenhum rate limiting no NGINX (spec 14.1). Nenhum SSE com `proxy_buffering off` e timeouts longos nas rotas de streaming (chat de construção `POST /api/agents/chat` e `POST /api/agents/{id}/chat`). `client_max_body_size` dimensionado para o upload de knowledge do contrato.

### 2.3 Contrato HTTP orchestrator -> worker (interno, NGINX :8081)

- **URL:** `POST http://nginx:8081/execute` (o server block interno remove qualquer prefixo; o worker expõe `POST /execute`).
- **Header obrigatório:** `X-Worker-Token: <WORKER_TOKEN>` (segredo compartilhado, vem do `.env` do orchestrator; o NGINX repassa, §1.5 do contrato exige que o NGINX tenha `WORKER_TOKEN` no ambiente).
- **Body:** `{ "agentId": "uuid", "nodeId": "node-1", "inputs": { ... }, "timeout": 60 }`.
- **Response 200:** `{ "status": "completed"|"failed", "outputs": { ... }, "action": "follow"|"return"|"finalize", "iterations": int, "logs": [str] }`.
- **Response 401:** `{ "error": "unauthorized", "code": "worker_token_invalid" }` (sem token / token errado).
- **Response 404:** `{ "error": "agent_not_found", "code": "agent_not_found" }` (agentId inexistente no MinIO).
- **Response 408/429/502:** erro estruturado; **nunca** stack trace cru.
- **Timeout:** por request; o orchestrator manda `timeout` no body.
- **Retry:** 3 tentativas, backoff 2s/4s/8s (no worker_client, §8).
- **Regra de ouro:** a node function **nunca** propaga exceção do worker. Erro do worker vira `{ status: "failed", error }` como state update; o grafo **não** aborta.

### 2.4 `.env.example` completo

```dotenv
# --- Banco (orchestrator) ---
# Driver asyncpg (conforme stack SQLAlechemy 2 async + asyncpg do contrato §3/§6).
DATABASE_URL=postgresql+asyncpg://agent_portal:agent_portal@postgres:5432/agent_portal

# --- Auth / JWT (orchestrator + portal) ---
JWT_SECRET=change-me-in-prod
NEXTAUTH_SECRET=change-me-in-prod
NEXTAUTH_URL=http://localhost/

# --- Worker (segredo compartilhado orchestrator<->worker, repelado pelo NGINX) ---
WORKER_TOKEN=change-me-in-prod

# --- MinIO (orchestrator e worker) ---
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=change-me-in-prod
MINIO_ENDPOINT=http://minio:9001
MINIO_BUCKET_AGENTS=agents
MINIO_BUCKET_SKILLS=skills
# (console/host, só para debug local)
MINIO_HOST_ENDPOINT=http://localhost:19001

# --- Admin (seed, orchestrator) ---
ADMIN_EMAIL=admin@local
ADMIN_PASSWORD=change-me-in-prod
ADMIN_NAME=Administrador

# --- LLM (orchestrator e worker) ---
LLM_PROVIDER=mock              # mock | openai
OPENAI_API_KEY=               # só se LLM_PROVIDER=openai
# O chat de construção e a execução de agentes usam o mesmo provedor.

# --- Embeddings (orchestrator e worker) ---
EMBEDDING_PROVIDER=mock        # mock | openai
EMBEDDING_DIM=1536             # dimensão fixa V1 (coluna vector(1536))
# Chave de embeddings = a mesma OPENAI_API_KEY do chat (um só provedor na V1, ver LLM acima).
# Só é preciso com EMBEDDING_PROVIDER=openai.

# --- CORS (orchestrator, defensivo; na prática mesma origem) ---
CORS_ORIGINS=http://localhost,http://localhost:80

# --- Notificação por email (desligado por padrão na V1) ---
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
ENABLE_EMAIL_NOTIFICATIONS=false

# --- Rivvn (gateado por contrato; fora do caminho crítico da V1) ---
RIVVN_CLIENT_ID=
RIVVN_CLIENT_SECRET=
RIVVN_BASE_URL=https://api.rivvn.ai
RIVVN_REDIRECT_URI=http://localhost/api/integrations/rivvn/callback
```

Notas: (a) com `LLM_PROVIDER=mock` / `EMBEDDING_PROVIDER=mock` **não** é preciso chave; com chave real o provedor real entra. (b) `JWT_SECRET` e `NEXTAUTH_SECRET` são o **mesmo valor** no `.env` (o JWT emitido pelo portal é validado pela API com `JWT_SECRET`). (c) O seed **não** cria nada se `ADMIN_EMAIL` ou `ADMIN_PASSWORD` faltarem.

---

## 3. Versões pinadas

Imagens: `python:3.11-slim`, `node:20-alpine`, `next:14` (Next.js 14 App Router), `pgvector/pgvector:pg15`, `nginx:1.27-alpine`, `minio/minio:RELEASE.2024.09.22T01.12.59Z`, `minio/mc:RELEASE.2024.09.22T00.31.45Z`. **Nota:** as versões de pacote abaixo são estáveis e pinadas; o nó `spike` re-verifica a superfície de API do LangGraph (streaming/interrupt) e o `infra-review` confirma a instalabilidade. Qualquer divergência fica registrada em §13.

**agent-orchestrator (pyproject.toml):**
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.2.35
asyncpg==0.30.0
psycopg[binary]==3.2.10
alembic==1.14.3
python-dotenv==1.0.1
pydantic==2.11.7
python-multipart==0.0.20
pyyaml==6.0.2
python-jose[cryptography]==3.3.0     # JWT na API (ou use pyjwt; o contrato exige JWT assinado)
python-json-logger==2.0.7            # logging estruturado
langgraph==0.2.61
langgraph-checkpoint==2.0.9
langgraph-checkpoint-postgres==2.0.10
langchain-core==0.3.28
pgvector==0.3.6                      # Vector() para o modelo
httpx==0.28.1
openai==1.58.1                       # cliente real (só usado se LLM_PROVIDER=openai)
bcrypt==4.2.0
minio==7.2.13
```
Dependências de teste: `pytest==8.3.4`, `pytest-asyncio==0.24.0`, `httpx`, `python-multipart`.

**agent-worker (pyproject.toml):** subconjunto do orchestrator: `fastapi`, `uvicorn`, `sqlalchemy` (não; o worker não usa SQLAlchemy), `httpx`, `pydantic`, `python-json-logger`, `langgraph`/`langgraph-checkpoint` (só se o loader/loop precisar — o worker é genérico, usa só LLM + tools), `minio`, `bcrypt`. O worker **não** precisa de Alembic nem langgraph-checkpoint-postgres: ele executa **um** agente e devolve; os checkpoints são responsabilidade do orchestrator. Lista recomendada:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.11.7
python-json-logger==2.0.7
httpx==0.28.1
minio==7.2.13
openai==1.58.1
pyyaml==6.0.2
```

**agent-portal (package.json):**
```
next@14.2.15
react@18.3.1
react-dom@18.3.1
next-auth@4.24.10          # v4, não v5
@xyflow/react@12.3.2        # React Flow (ADR-006)
lucide-react@0.468.0
```
Dev: `typescript`, `eslint`, `eslint-config-next`, `vitest@2.1.8`, `@testing-library/react@16.1.0`, `@testing-library/jest-dom@6.6.3`, `@playwright/test@1.49.1`, `jsdom`, `@types/react`, `@types/node`.

**Convenções de transição (LangGraph):** streaming via `graph.astream(event_filter, config)` (ou `stream_events` de `langchain-core`); detecção de interrupção via `stream.interrupted` / `stream.interrupts` (confirme no spike). Comandos de roteamento via `Command(goto=<node_id_real>)` e `Command(resume=<valor>)`. Reducer padrão `last` (overwrite); `iterations` usa reducer de soma `Annotated[int, operator.add]`.

---

## 4. Ambiente de desenvolvimento e testes (crítico: dezenas de agentes em paralelo)

**Regra de ferro (protocolo comum §4):** nós de implementação **nunca** rodam `docker compose up --build`, `docker compose down`, `docker system prune`, `npm install`/`npm ci`, `pip install` de pacote novo nem `npm run build`. Eles usam os containers já de pé (`docker compose exec`, `docker compose run --rm`) e dependências já instaladas. Subir/reconstruir/instalar é dos **revisores de fase** e dos nós donos (infra-docker, fe-shell, revisores).

**`docker-compose.override.yml` (dev, dono: infra-docker):** bind mount do código nos três serviços; `orchestrator` e `agent-worker` com `uvicorn ... --reload`; `portal` com `next dev --0.0.0.0:3000`. Mudança de código não exige rebuild. Contêineres não expõem porta no host (exceto NGINX :80); o acesso é pelo NGINX.

**Onde rodar testes:**
- **Backend (orchestrator e worker):** **dentro do container** (`docker compose run --rm orchestrator pytest <caminho>` e `docker compose run --rm agent-worker pytest <caminho>`), porque o host tem Python 3.13 e as imagens 3.11. Scripts dentro de containers usam fim de linha **LF** (`.gitattributes`).
- **Frontend (portal):** no **host**, `npx vitest run` e `npx tsc --noEmit` com `node_modules` já instalado (fe-shell rodou `npm install`). `npm run build` é do revisor de frontend, não dos nós de tela.
- **A partir de um worktree** (ajuste do flow de 2026-09-24; nós de implementação trabalham em `../squad-agentica.worktrees/<id>`, branch `wt/<id>`, e fazem merge no `main` ao terminar): backend com `docker compose -p squad-agentica run --rm --no-deps <serviço> pytest <caminho>` executado dentro do worktree. O `-p` reaproveita a rede e o banco do stack de pé, o bind mount resolve para o código do worktree e `--no-deps` impede recriar serviços cujos mounts apontariam para o worktree. `docker compose exec` testa o código do `main`, não o do worktree. Frontend com `node_modules` do worktree como junction para `agent-portal/node_modules` do checkout principal (`tsc` e `vitest` validados assim); na limpeza, a junction sai com `cmd /c rmdir` sem `/s` antes do `git worktree remove`, que não a remove. O `.env` é copiado da raiz para o worktree.

**Banco de teste isolado (obrigatório):** cada sessão de pytest cria **um banco próprio com sufixe único** (ex.: `agent_portal_test_<uuid>`) e o destrói no teardown (fixture `pytest_asyncio` com `scope="session"`/`function`, conforme contrato). O fixture usa o mesmo `DATABASE_URL` base mudando apenas o nome do banco, com permissão do usuário de teste de criar bancos (ver `postgres/init.sql`). **Nunca** use o banco `agent_portal` em teste. O LangGraph `PostgresSaver` também aponta para o banco de teste (cria suas tabelas via `setup()`, §8).

**Provedores mock (obrigatórios nos testes e E2E):**
- `app/core/llm.py`: interface `LLMClient.chat(...)` + fábrica `get_llm_client()`. Provider `mock` = `MockLLMClient`: respostas **determinísticas**. Sustenta (a) o chat de construção (devolve um draft coerente a partir da mensagem do usuário) e (b) a execução de agentes (devolve um output estruturado derivado dos `inputs` + um marker verificável nos testes). Provider real só entra se `LLM_PROVIDER=openai` **e** `OPENAI_API_KEY` estiver presente.
- `app/core/embeddings.py`: interface `Embedder.embed(text)->list[float]` + `embed_batch` + `dim` + fábrica `get_embedder()`. Provider `mock` = `MockEmbedder`: vetor determinístico da dimensão `EMBEDDING_DIM` (ex.: hash normalizado do texto), sempre normalizado antes do insert.
- Testes e E2E rodam com `LLM_PROVIDER=mock` e `EMBEDDING_PROVIDER=mock`. Com chave real no `.env`, o provedor real é usado (nenhum teste exige chave real; os mocks sustentam tudo).

**Migrations no startup:** o entrypoint do container do orchestrator (Dockerfile, dono: infra-docker) roda `alembic upgrade head` e o **seed** (`python -m app.db.seed`) **antes** do `uvicorn`, tolerando a inexistência temporária de tabelas. **Dono do entrypoint: infra-docker**; db-migrations configura o Alembic.

**`.gitattributes` (dono: infra-docker):**
```
*.sh text eol=lf
Dockerfile text eol=lf
docker-compose*.yml text eol=lf
```

---

## 5. Autenticação

Base: spec §3 + §14.1. **NextAuth.js v4** (não v5), provider `credentials`, `session.strategy="jwt"`, `pages.signIn="/login"`.

**Fluxo (nunca localStorage/sessionStorage):**
1. O usuário loga no portal (formulário `credentials`). O `authorize()` do NextAuth (servidor do portal, `app/api/auth/[...nextauth]/route.ts`) chama `POST <ORCHESTRATOR_API_URL>/api/auth/login` (URL interna, de dentro do container do portal — **não** `localhost`). O backend valida bcrypt contra o `User` (seed) e devolve access + refresh tokens da API.
2. Access e refresh da API ficam **dentro do JWT da sessão NextAuth**, nos callbacks `jwt` e `session`. O callback `jwt` faz **rotação de refresh**: quando o access expirar, cunha um novo access usando o refresh; se o refresh falhar, marca a sessão com erro e força novo login.
3. O cliente obtém o token para chamadas REST e WebSocket por um route handler do portal: **`GET /api/session-token`** (donos de rota: infra-nginx rota para o portal, §2.2 regra 2). Ele devolve o JWT da sessão (que carrega os tokens da API) via Response (cookie `NEXTAUTH_SESSION_TOKEN` já vem do NextAuth; o handler o extrai ou o cunha a partir da sessão). **Nunca** localStorage. O token vive em memória no JS.

**Orchestrator (`app/auth/`, dono: auth-backend):**
- `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me`; validação com `JWT_SECRET`.
- Claims: `sub` (ownerId), `iat`, `exp`; tipo distinto `typ` = `"access"` vs `"refresh"`; exp curta (15 min) para access, longa (7 dias) para refresh. Rotação de refresh: refresh token usado é invalidado após uso (ou rotacionado; defina e teste — o contrato exige que o refresh antigo **não** devolva o mesmo refresh antigo reutilizável indefinidamente).
- `get_current_user` (dependência FastAPI): protege **opt-out** — toda rota exige usuário exceto `/api/auth/*` (register/login/refresh) e health checks. Um router novo criado por outro nó **nasce protegido** (dependência global com lista de exceções; teste isso).
- Validação de token para o WebSocket (função reutilizável, chamada pelo `rt-websocket` no handshake).
- Rate limiting do login (spec 14.1), 429 no envelope. Mensagens genéricas (não revelam se o e-mail existe); nunca logar senha nem token.

**Hash de senha:** bcrypt **custo 12** em `app/core/security.py` (`hash_password`, `verify_password`), usado pelo **seed** e pelo **login**. **Dono de `app/core/*`: infra-docker** (o auth-backend consome a interface; se precisar mudar a assinatura, pede ao dono).

**Rotação de sessão vs. JWT:** revogação de sessão NextAuth não invalida JWT já emitido (JWT é stateless) — aceitável em V1 single-user; documentado.

---

## 6. Decisões que fecham os riscos da análise de prontidão (ADR curtas)

Cada ADR tem contexto, decisão e consequência. São **bloqueantes** para compiler/runtime/HITL.

> **Nota de numeração (importante):** a numeração ADR deste contrato (ADR-001..ADR-011) é **independente** da numeração ADR da spec (ADR-001..ADR-011): por exemplo, "ADR-002 da spec" (contrato de entrada/saída dos agentes) **não é** "ADR-002 deste contrato" (schema fixo). Sempre que citar, diga explicitamente "ADR-00X do contrato técnico" ou "ADR-00X da spec". A tabela de equivalências está em §11.

### ADR-001 — Worker: node function nunca levanta exceção
- **Contexto (V-01/risco #1 da análise):** `await worker_client.execute()` dentro de node function; se o worker cair, exceção aborta o `astream` inteiro e deixa o checkpoint inconsistente.
- **Decisão:** a node function é sempre **cercada** por try/except, **nunca** propaga exceção para o LangGraph. Falha do worker / timeout vira state update `{"status":"failed","error":"..."}`; a `route_fn` manda para `END`. O stream termina limpo, o run fica retomável.
- **Consequência:** nó falho **não** aborta o grafo; checkpoint anterior survive; retomada possível. Teste obrigatório (spike + runtime): worker fora do ar -> nó `failed`, run pausado, retomável.

### ADR-002 — State schema FIXO (nunca TypedDict dinâmico)
- **Contexto (risco #2):** `types.new_class()` quebra no checkpoint round-trip (schema muda entre compile e resume) e no PostgresSaver.
- **Decisão:** um `State` com estrutura **genérica e fixa** —
```python
# app/compiler/state.py
State = TypedDict("State", {
    "data": dict,                                   # ports namespaced por nodeId (merge de escrita, padrão LangGraph)
    "actions": dict,                              # {nodeId: "follow"|"return"|"finalize"}
    "status": dict,                               # {nodeId: "completed"|"failed"|"interrupted"}
    "iterations": Annotated[dict, operator.add],  # {nodeId: int} (reducer de soma, ADR-005)
    "max_iter_exceeded": Annotated[bool, operator.or_],
    "pipeline_status": str,                       # "running"|"completed"|"failed"
})
```
- O namespace `{nodeId}` vira **convenção dentro dos valores do dict**, não feature de schema (ADR-003).
- **Consequência:** schema estável survive recompilações; PostgresSaver serializa sem perda.

### ADR-003 — Namespace por nodeId é convenção de valor, não de schema
- **Contexto:** spec 4.2 quer `{nodeId}.inputs.{port}`; D8 alerta TypedDict dinâmico.
- **Decisão:** o State tem keys fixas (`data`, `actions`, `status`, `iterations`, ...); os **valores** são dicts indexados por nodeId (`state["data"][nodeId]`). Namespacing dentro de `data`, nunca no schema.
- **Consequência:** mesmo agente em dois nós não colide; schema único para todo o grafo.

### ADR-004 — Resume sempre recompila o grafo (compile_and_resume)
- **Contexto (risco #3):** StateGraph com node functions não é serializável; não sobrevive a restart de processo.
- **Decisão:** persistir **apenas** o JSON da pipeline + estado (via LangGraph checkpointer por `thread_id`); reconstituir o `StateGraph` via `compile_pipeline(json)` em todo execute/resume/checkpoint-resume/`compile_and_resume(thread_id, resume)`.
- **Consequência:** run sobrevive a restart; sem pickle de grafo; idempotência garantida pelo checkpointer.

### ADR-005 — `maxIterations` checado na node function; `iterations` usa reducer de soma
- **Contexto (risco #5):** enforcement ambígua; reducer `last` perde contagem;
- **Decisão:** node function checa `iterations[nodeId] >= maxIterations` **no início** (ADR-007); se excedido, `route_fn` manda para `END` **antes** de chamar o worker. `iterations` como `Annotated[dict, operator.add]` (soma), não `last`. A `route_fn` principal de cada nó define precedência: maxIterations -> END primeiro, depois conditions, depois `follow`.
- **Consequência:** anti-loop consistente; contador survive checkpoints; `iterations` sempre JSON-serializável.

### ADR-006 — `Command(goto=...)` só com IDs reais de nós; rejectTarget configurável na aresta
- **Contexto (risco #4 + Analysis X-02):** strings literais `"proceed"`/`"reject_handler"` não são nós.
- **Decisão:** `approval_node_{edgeId}` devolve `Command(goto=target_node_id)` (aprovar) e `Command(goto=reject_target)` (rejeitar). `rejectTarget` é **configuração da aresta** (`PipelineEdge.rejectTarget`); default: loop-back para o source, exceto se `condition.field=="action"` e `value=="return"` (então `END`).
- **Consequência:** `goto` sempre aponta para nó real; sem hardcoded.

### ADR-007 — `maxIterations <` checado no início (guarda de segurança)
- **Contexto (risco #5):** loop pode exceder o limite;
- **Decisão:** no início da node function, ler `state["iterations"][nodeId]` e comparar com `agent.maxIterations`; `>=` -> `route_fn` manda para `END` antes de rodar o agente; nunca raise; node function **não** incrementa `iterations` se já excedeu (deixa o `route_fn` decidir).
- **Consequência:** limite respeitado; loop cortado limpo.

### ADR-008 — Loader roda no worker (não no orchestrator)
- **Contexto (risco #10 + Analysis):** `loader.load()` é pesado (download skills, MCP, RAG); se orquestrar no orchestrator consome o event loop do grafo.
- **Decisão:** o orchestrator envia `agentId` + `inputs` + `timeout` ao worker; o **worker** (`app-worker/app/loader.py`) faz `loader.load(agent_snapshot) -> AgentCapabilities`, executa o agente (`Agent.run(inputs, capabilities)`), devolve output + action + logs. Worker baixa `.yml`/`.md` do MinIO por conta própria; cache local por versão + TTL.
- **Consequência:** orquestrador leve; worker autosuficiente; estado (checkpoints) continua no orchestrator (ADR-004).

### ADR-009 — Criação da ApprovalRequest pelo executor, upsert pós-interrupção
- **Contexto (spec 5.3 vs ADR-002 da análise):** spec 5.3 passo 3 diz que o orquestrador cria o ApprovalRequest **após** a pausa; mas idempotência diz "no bloco de retomada" (só acontece depois da resposta humana, impossível). O nó de aprovação **não** tem efeitos colaterais antes do `interrupt()`.
- **Decisão:** o **executor**, ao detectar a interrupção no stream, faz **upsert** da `ApprovalRequest` com chave `(runId, nodeId, interruptId)` e dispara a notificação (`approval:new`). Reexecuções do nó não duplicam (upsert idempotente). O resume (`compile_and_resume`) lê essa ApprovalRequest. Notificação só após upsert (ADR-002). Retomada usa essa ApprovalRequest (ADR-004).
- **Consequência:** sem duplicata de aprovação/notificação em resume; idempotência garantida por chave.

### ADR-010 — entryNodeId explícito (não inferido)
- **Contexto (Analysis X-08; spec 4.2):** `PipelineEntry.entryNodeId` define qual nó roda primeiro; compiler **não** infere.
- **Decisão:** `entryNodeId` (UUID, PipelineEntry) é campo obrigatório; compiler usa `add_edge(START, entryNodeId)`; grafo sem entryNodeId -> erro de validação (regra 5 do validador).
- **Consequência:** topologia determinística; nó de entrada não ambíguo.

---

## 7. Protocolo do WebSocket

**Conexão única:** `wss(s)://<host>/api/ws?token=<JWT>`. JWT validado no handshake (função reutilizável do auth-backend). Token inválido: close com código **policy violation**. Conexão associada a **um** owner (`ownerId`).

**Frames:** `"{\"channel\": <string>, \"data\": <any>}"`. Canal e data. Nada mais.

**Canais (exatamente spec 9.7):**

| Canal | Direção | Payload |
|---|---|---|
| `pipeline:status` | Server->Client | `{ "pipelineId": str, "runId": str, "nodeId": str, "status": "pending"|"running"|"completed"|"failed"|"waiting_approval", "at": iso8601 }` |
| `pipeline:log` | Server->Client | `{ "pipelineId": str, "runId": str, "nodeId": str, "level": str, "message": str, "at": iso8601 }` |
| `agent:output` | Server->Client | `{ "pipelineId": str, "runId": str, "nodeId": str, "output": any }` |
| `approval:new` | Server->Client | `{ "approvalId": str, "pipelineId": str, "runId": str, "nodeId": str, "message": str, "at": iso8601 }` |
| `approval:resolved` | Server->Client | `{ "approvalId": str, "pipelineId": str, "runId": str, "nodeId": str, "decision": "approved"|"rejected"|"revised", "at": iso8601 }` |

**Filtro:** server **filtra** eventos por ownerId; cliente escuta todos os canais, mas só recebe eventos de sua pipeline.

**Inscrição:** cliente **não** manda mensagem de subscribe — o servidor envia eventos de **todas** as pipelines do owner; o cliente filtra pelo `pipelineId` do payload. O `ConnectionManager` (websocket.py, dono: rt-websocket) mantém set de conexões por owner; `publish(owner_id, channel, data)` é a interface que executor/HITL consomem.

**Reconexão:** cliente refaz `GET REST` (`/api/pipelines/{id}` + `/api/pipelines/{id}/runs`) para sincronizar estado após reconectar; backoff exponential (1s,2s,4s,...,30s); token reenviado na reconexão. Heartbeat/ping para NGINX não derrubar ociosas.

**Dono do WebSocket:** `app/runtime/websocket.py` (`ConnectionManager`, `publish`) e router `app/api/ws.py` — **rt-websocket**. Executor (rt-executor) e HITL (hitl-approval) chamam `publish`.

---

## 8. Convenções transversais

**Envelope de erro (todas as APIs):** `{ "error": string, "code": string, "details"?: object }`.
- 400 `{ "error": "validation error", "code": "invalid_graph", "details": { "errors": [ { "rule": int, "message": str, "nodeId"?: str, "edgeId"?: str } ] } }` (formato de validação de grafo da spec 4.2, dentro de `details.errors`).
- 401 `{ "error": "unauthorized", "code": "not_authenticated" }`.
- 403 `{ "error": "forbidden", "code": "forbidden" }`.
- 404 `{ "error": "not_found", "code": "<recurso>_not_found" }`.
- 409 `{ "error": "conflict", "code": "<pipeline_already_running|already_responded|graph_running>", "details"?: object }`.
- 422 `{ "error": "unprocessable", "code": "<schema_validation>", "details": { "errors": [...] } }`.
- 429 `{ "error": "rate_limited", "code": "rate_limited", "details": { "retryAfter": int } }`.
- 500 `{ "error": "internal error", "code": "internal_error" }` (sem stack trace para o cliente; log no servidor).

**JSON em camelCase** em toda a API (ex.: `owner_id` no banco vira `ownerId`; `source_output` vira `sourceOutput`; `requires_approval` -> `requiresApproval`). Um único esquema (Pydantic model com `alias=`, ou `model_dump(by_alias=True)`). Manter por toda a V1.

**Paginação:** `{ "items": [...], "total": int, "page": int, "limit": int }`. Query: `?page=&limit=`. Listagens: `GET /api/agents`, `GET /api/pipelines`, `GET /api/approvals?status=pending|resolved|cancelled&pipelineId=&page=limit=`.

**Datas:** ISO 8601, UTC, `Z` explícito (ex.: `2026-09-22T13:45:00Z`).

**IDs:** UUID v4 em todos os ids (`agentId`, `pipelineId`, `nodeId`, `runId`, `approvalId`, `interruptId`, etc.).

**Logs estruturados:** JSON no stdout (`python-json-logger`); campos `{timestamp, level, message, pipeline_id?, run_id?, agent_id?}`; **sem segredos** (nunca token, senha, credencial).

**Rate limiting (spec 14.1, na aplicação):** chat 30/min, execute 5/min, upload 10/min. Em 429 com envelope acima. Contador em memória (V1 single-user). Não no NGINX.

**Concorrência (409):** execute sobre pipeline `running` -> 409 `pipeline_already_running`; `PUT /pipelines/:id` durante run -> 409 `graph_running`; responder aprovação respondida / a um run cancelado -> 409 `already_responded`.

**Lint / type-check:** ruff + mypy (ou pyright) no backend; eslint + `tsc --noEmit` no portal. Rodar antes de declarar pronto.

---

## 9. Mapa nó -> dono de arquivos

**Regra:** cada nó implementa **só** seus arquivos. Arquivos compartilhados são de um só dono (abaixo). Se um nó precisa tocar num arquivo de outro, pede **na resposta final**; o dono aplica. Mesma fase = mesmo revisor, mas **sem** sobreposição de arquivos.

### FASE 1 — Infra (revisor: infra-review)

| Nó | Cria/altera | Não toca |
|---|---|---|
| **infra-docker** | `docker-compose.yml`, `docker-compose.override.yml`, `.env.example`, `.dockerignore`, `.gitignore`, `.gitattributes`, os 3 Dockerfiles, `agent-orchestrator/app/main.py` (descoberta de routers), `agent-orchestrator/app/core/*` (config, security, errors, llm, embeddings), `agent-orchestrator/app/__init__.py`, `agent-orchestrator/pyproject.toml`, `agent-worker/app/*` (scaffold health), `agent-worker/pyproject.toml`, `agent-portal/{app/page.tsx, app/layout.tsx, package.json, package-lock.json, tsconfig.json, next.config.ts}`, skeleton `alembic/`, `tests/` health | `nginx/*`, `postgres/*`, `minio/*`; `app/api/*` (outros nós); `app/db/models.py`; `agent-portal/app/globals.css` |
| **infra-postgres** | `postgres/init.sql`, `postgres/README.md` | nada fora de `postgres/` |
| **infra-minio** | `minio/init-buckets.sh`, `minio/README.md` | nada fora de `minio/` |
| **infra-nginx** | `nginx/nginx.conf`, `nginx/conf.d/*.conf`, `nginx/README.md` | nada fora de `nginx/` |

> **Compartilhado da FASE 1:** infra-docker é dona de `docker-compose*`, Dockerfiles, `.env.example`, `.gitignore/.dockerignore/.gitattributes`, `agent-orchestrator/{app/main.py, app/core/*, pyproject.toml}`, `agent-worker/{pyproject.toml}`, `agent-portal/{package.json, package-lock.json, tsconfig.json, next.config.ts, app/layout.tsx, app/page.tsx}`, skeleton `alembic/`. infra-nginx: `nginx/*`. infra-postgres: `postgres/*`. infra-minio: `minio/*`.

### FASE 2 — DB (revisor: db-review)

| Nó | Cria/altera |
|---|---|
| **db-models** | `agent-orchestrator/app/db/models.py`, `app/db/session.py` |
| **db-migrations** | `agent-orchestrator/alembic/env.py`, `alembic/versions/0001_initial.py` (donos do Alembic) |
| **db-seed** | `agent-orchestrator/app/db/seed.py` |

### FASE 3 — Auth (revisor: auth-review)

| Nó | Cria/altera |
|---|---|
| **auth-backend** | `agent-orchestrator/app/auth/*`, `app/api/auth.py` (consome `app/core/*`) |
| **auth-frontend** | `agent-portal/{auth-options.ts, types/next-auth.d.ts, app/api/auth/[...nextauth]/route.ts, middleware.ts, components/auth/SessionProvider.tsx, lib/auth-client.ts, app/(auth)/login/page.tsx, app/(auth)/register/page.tsx` |

### FASE 4 — Backend CRUD (revisor: be-review)

| Nó | Cria/altera |
|---|---|
| **be-agents** | `app/api/agents.py`, `app/agents/*` (base, built-ins, validator, storage MinIO) |
| **be-skills** | `app/skills/registry.py`, `app/api/skills.py`, `app/tools/*`, `app/mcp/*`, `app/api/tools.py`, `app/api/mcp_servers.py` |
| **be-knowledge** | `app/knowledge/*`, `app/api/knowledge.py` |
| **be-integrations** | `app/api/integrations.py`, `app/integrations/*` |

### FASE 5 — Pipeline engine (revisor: pe-review)

| Nó | Cria/altera |
|---|---|
| **pe-compiler** | `app/compiler/state.py`, `app/compiler/graph_builder.py` |
| **pe-validator** | `app/compiler/validator.py` (consome; **não** cria arquivo em `app/api/`; o endpoint de validação vive em `app/api/pipelines.py`, do rt-executor) |
| **pe-loader** | `app/skills/loader.py` (+ model `AgentCapabilities` onde o contrato definir, tipicamente `app/compiler/state.py` ou `app/agents/*`) |

### FASE 6 — Runtime (revisor: rt-review)

| Nó | Cria/altera |
|---|---|
| **rt-executor** | `app/runtime/executor.py`, `app/runtime/checkpoint.py`, `app/runtime/worker_client.py`, `app/api/pipeline_runs.py` (execute/pause/resume/stop/runs/checkpoints) |
| **rt-worker** | `agent-worker/app/*` (main, worker, minio_client, loader) |
| **rt-websocket** | `app/runtime/websocket.py` (`ConnectionManager`, `publish`), `app/api/ws.py` |

### FASE 7 — HITL (revisor: hitl-review)

| Nó | Cria/altera |
|---|---|
| **hitl-approval** | `app/approvals/node_function.py`, `app/approvals/service.py`, `app/api/approvals.py` |
| **hitl-notification** | `app/notifications/*` |
| **hitl-resume** | `app/approvals/resume.py` |

> **Aprovação:** o nó de aprovação é **usado** pelo compiler (`graph_builder.py`), mas implementado pelo hitl-approval (contrato: compiler gera topologia `approval_node_{edgeId}`, hitl-approval entrega a função). O executor (rt-executor) expõe o **hook** de interrupção; hitl-approval implementa-o (upsert + notificação). O `publish` para notificação vem de `app/runtime/websocket.py` (rt-websocket), consumido por hitl-approval/hitl-notification.

### FASE 8 — Portal frontend (revisor: fe-review)

| Nó | Cria/altera |
|---|---|
| **fe-shell** | `app/layout.tsx`, `app/globals.css`, `components/layout/*`, `components/ui/*`, `lib/api.ts`, `lib/websocket.ts`, `lib/types.ts`, `agent-portal/README.md`, **páginas placeholder** para todas as rotas do PLANO-FRONTEND (com empty state) |
| **fe-dashboard** | substitui `app/(dashboard)/page.tsx` (placeholder do shell) |
| **fe-agents** | `app/(dashboard)/agents/*` (new, [id]), `components/AgentChat.tsx`, `components/AgentPreview.tsx` |
| **fe-flow-editor** | `app/(dashboard)/pipelines/[id]/page.tsx`, `components/FlowEditor.tsx`, `components/EdgePanel.tsx` |
| **fe-monitor** | `app/(dashboard)/pipelines/[id]/run/page.tsx`, `components/PipelineMonitor.tsx` |
| **fe-approvals** | `app/(dashboard)/approvals/page.tsx`, `components/ApprovalPanel.tsx` (pode tocar mínimamente no badge do header do shell) |
| **fe-library** | `app/(dashboard)/{skills,tools,mcp,knowledge}/page.tsx`, `components/{SkillsLibrary,ToolsEditor,MCPServersLibrary,KnowledgeView}.tsx` |

> **Compartilhado do portal:** `package.json`/`package-lock.json`/`tsconfig`/`next.config` — infra-docker; `globals.css`/`layout.tsx`/`components/layout`/`components/ui`/`lib/*` — fe-shell. Nenhum nó de tela instala dependência (fe-shell instala `@xyflow/react` etc.).

### Ajuste do flow (2026-09-24): nós divididos

Cinco nós foram divididos para reduzir o escopo de cada agente. Esta tabela **prevalece** sobre as linhas correspondentes acima.

| Nó | Cria/altera | Observação |
|---|---|---|
| **be-agents** | `app/api/agents.py`, `app/agents/*` exceto `app/agents/chat/` | CRUD, validador, storage, classes base e o service de agentes. Sem chat. |
| **be-agent-chat** (novo, roda depois de be-agents) | `app/api/agent_chat.py`, `app/agents/chat/*` | `POST /api/agents/chat` e `POST /api/agents/{id}/chat` (SSE), rate limit do chat. Salva pelo service de be-agents. Revisor: be-review. |
| **rt-checkpoint** (novo) | `app/runtime/checkpoint.py`, `app/runtime/worker_client.py` | Saem de rt-executor. Revisor: rt-review. |
| **rt-executor** (roda depois de rt-checkpoint) | `app/runtime/executor.py`, `app/api/pipeline_runs.py` | |
| **fe-flow-editor** | `app/(dashboard)/pipelines/page.tsx`, `app/(dashboard)/pipelines/[id]/page.tsx`, `components/FlowEditor.tsx`, `components/flow/*` exceto validação | Canvas, paleta, conexões, salvar, desfazer e refazer. |
| **fe-flow-edges** (novo, roda depois de fe-flow-editor) | `components/EdgePanel.tsx`, `components/flow/validation*` | Pode editar `FlowEditor.tsx` e `pipelines/[id]/page.tsx` só para plugar painel, validação e executar. |
| **qa-fix** | correções de falhas críticas e altas | |
| **qa-fix-rest** (novo, roda depois de qa-fix) | correções de falhas médias e baixas | Roda todas as suítes e o build no fim. |

**Revisores da FASE 8:** `fe-review-editor` (novo) julga fe-flow-editor, fe-flow-edges e fe-monitor; `fe-review` julga fe-dashboard, fe-agents, fe-approvals e fe-library, e aprova o portal inteiro. `qa-final` rejeita para qa-fix e qa-fix-rest.

---

## 10. Fora da V1

- **Rivvn:** fora do caminho crítico. Mantido o `source: "rivvn"` no `PipelineEdge`/`KnowledgeRef`; UI **desabilitada** com mensagem "contrato comercial ativo necessário"; API responde erro claro (`403` / mensagem "não disponível na V1"). Sem SDK externo na V1.
- **Notificações:** **in-app** (WebSocket) é o canal da V1. **email** só se simples (desligado por padrão; SMTP por env; `ENABLE_EMAIL_NOTIFICATIONS=false`). **Teams/Slack** são stubs para V2.
- **Single-user:** V1 é single-user (`ownerId` fixo = o admin). Sem multi-tenant, sem RBAC, sem SSO.
- **Sem versionamento de pipelines:** pipelines não versionadas na V1. `PUT` de pipeline durante run -> 409 `graph_running` (spec 14.1). Re-executar cria novo run (spec 4.2).
- **Outros:** sem marketplace de tools, sem métricas/analytics, sem agentes "meta", sem integração Azure/GitLab/Slack/Teams na V1 (apenas GitHub leitura).

---

## 11. Divergências resolvidas

Cada contradição entre spec / plano / domínios / análise, com a escolha e o motivo. A spec e os planos **não** são alterados aqui (o contrato prevalece); estas são as resoluções aplicadas.

1. **HITL: `interrupt()` é de nó, não de aresta (V-01).** Spec 5.3 fala em chamar `interrupt` na aresta; LangGraph só permite dentro de node function. **Escolha:** compiler gera um **nó de aprovação** `approval_node_{edgeId}` (ADR-006 da spec + ADR-009 deste contrato); a decisão de aprovação vive na **aresta** (`requiresApproval`), mas a **primitiva** `interrupt()` roda no nó. Resolvido por ADR-002/ADR-009.
2. **Retomada re-executa o nó; duplicata de ApprovalRequest (V-02).** **Escolha:** efeitos colaterais (criar ApprovalRequest + notificar) **após** o `interrupt()`, com upsert idempotente de chave `(runId, nodeId, interruptId)` (ADR-009). Idempotência garantida por chave, não por posição.
3. **Campo `capabilities`/mochila sem dono (X-01).** **Escolha:** capacidades são **derivadas em runtime**, nunca persistidas no snapshot; `loader.load()` roda **no worker** (ADR-008). Snapshot carrega só os campos da spec; `capabilities` não é campo do modelo.
4. **Aresta `D8 -> D6` ausente (X-02).** **Escolha:** D6 depende de D5 **e** D8 (loader). A ordem de fases respeita isso; o loader (FASE 4) está pronto antes do runtime (FASE 6). Documentado no mapa de fases do §9.
5. **Shell dá execução arbitrária a todo agente (L-02).** **Escolha:** `shell` é **opt-in por agente** (`shellAccess: boolean`, default `false`); quando habilitada, diretório restrito + blocklist + timeout 30s + sem acesso a secrets (spec 6.3 + 14.1). Dado externo delimitado por `<<<EXTERNAL_DATA>>>` (spec 14.1). Documentado como risco residual de sandbox em D8.
6. **KnowledgeBase sem model/API (L-03).** **Escolha:** model `KnowledgeBase` + `KnowledgeDocument` (spec 4.6, já nos domínios); API CRUD completa em `app/api/knowledge.py` (spec 9.3). Resolvido.
7. **`NotificationChannel` nunca declarado (C-01).** **Escolha:** `NotificationChannel = "in-app"|"email"|"teams"|"slack"` (tipo no `AgentSnapshot`; V1 só in-app + email). Resolvido em §9/§5.
8. **`AgentSnapshot` e `Agent.requiresApproval` duplicado (C-09).** **Escolha:** `requiresApproval` vive **só** na `PipelineEdge` (spec 4.2 + §16 da spec). `Agent.requiresApproval` é removido como gatilho; o gate é da aresta. Resolvido.
9. **`maxIterations` duplicado compiler/runtime (X-08).** **Escolha:** enforcement **exclusiva** no runtime via node function no início + reducer de soma (ADR-005/ADR-007). Compiler só topologia; `route_fn` aplica a guarda antes de rodar o agente. Sem dual-enforcement.
10. **State TypedDict dinâmico vs. checkpoint (risco #2).** **Escolha:** schema **fixo** com namespaces como convenção de valor (ADR-002/ADR-003). Resolvido.
11. **Grafo compilado não persistível (risco #3).** **Escolha:** recompilar sempre do JSON (`compile_and_resume`, ADR-004). Resolvido.
12. **`Command(goto="proceed")` sem nó real (risco #4).** **Escolha:** `goto` só com IDs reais; `rejectTarget` configurável na aresta (ADR-006). Resolvido.
13. **Socket.IO vs WebSocket nativo (V-08).** **Escolha:** **WebSocket nativo** (spec 9.7). Socket.io **não** entra. Resolve o V-08.
14. **Portas e pgvector (V-06/infra).** **Escolha:** imagem `pgvector/pgvector:pg15` (inclui a extensão `vector`); `langgraph-checkpoint-postgres` nas dependências do orchestrator (spec 12). Portas host: Postgres 15432, MinIO 19001/19002. Resolvido.
15. **Chat de construção sem `:id` (L-04).** **Escolha:** `POST /api/agents/chat` (sem id) cria sessão efêmera/draft; `POST /api/agents/:id/chat` para editar. Resolvido.
16. **`GET /api/agents` e `GET /api/pipelines` ausentes (L-05/X-06).** **Escolha:** incluídos (paginação, §8). Resolvido.
17. **Fim de linha (protocolo comum §5).** **Escolha:** `.gitattributes` com `*.sh`/Dockerfiles/compose em `eol=lf`; containers usam LF. Resolvido.
18. **Gateway do worker pela :80 (risco de segurança).** **Escolha:** worker **não** é acessível pela :80; orchestrator o chama por server block interno NGINX :8081 com `X-Worker-Token` (§2.3). Resolvido.
19. **`ownerId` sem valor (L-08).** **Escolha:** V1 single-user; `ownerId` do admin (seed) é o `sub` do JWT. Listagens filtram por `ownerId`. Resolvido.
20. **Rate limiting sem envelope claro (L-14).** **Escolha:** 429 com envelope `"error"/"code"/"details.retryAfter"` (§8). Resolvido.

---

## 12. Resposta final (contúdo integral)

Este documento **é** o conteúdo integral do contrato. As seções 0–11 acima devem ser lidas na íntegra por todos os nós do flow. As resoluções de risco são: ADR-001 (worker sem exceção), ADR-002 (schema fixo), ADR-003 (namespace por valor), ADR-004 (recompilar no resume), ADR-005 (maxIterations + reducer de soma), ADR-006 (goto com IDs reais), ADR-007 (guarda no início), ADR-008 (loader no worker), ADR-009 (ApprovalRequest upsert pós-interrupt), ADR-010 (entryNodeId explícito), ADR-011 (WebSocket nativo).

## 13. Pendências (revisores de fase)

Resumindo as 8 críticas da análise de prontidão: V-01 (interrupt de nó, ADR-002), V-02 (idempotência por chave, ADR-009), X-01 (mochila derivada no worker, ADR-008), X-02 (dependência D8->D6 documentada), L-01 (GitHub via `app/api/integrations.py`, fase 4), L-02 (shell opt-in, ADR-002 de segurança), L-03 (model+API KnowledgeBase, fase 4), C-01 (`NotificationChannel` declarado, §9).

**Não resolvidos (registrados para revisores/fases seguintes):**
- **spike:** re-verificar a superfície exata de API do LangGraph (versão pinada, streaming/interrupt) e registrar divergência no README do spike.
- **infra-review:** confirmar versions de imagem e instalabilidade dos pacotes pinados; healthchecks com binários existentes.
- **fe-review / pe-review / rt-review / hitl-review:** validar os handoffs e gerar o `GUIA-API-FRONTEND.md` (spec 9 inteira + eventos, do hitl-review).

> **Regra de precedência:** em caso de conflito entre este contrato, a spec, os planos D1–D10, `PLANO-BACKEND.md`, `PLANO-FRONTEND.md` e `DESIGN-SYSTEM.md`, **vale o de maior precedência:** (a) este contrato, (b) spec, (c) domínios + plano de execução, (d) `PLANO-BACKEND`/`PLANO-FRONTEND`/`DESIGN-SYSTEM`, (e) este prompt. Todo desvio registrado aqui (ou na resposta do nó que detectou).
