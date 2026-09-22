# D1 — Infraestrutura & Setup

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 1 · Fundação**. Dependência: nenhuma.
> Base: spec `2026-09-17-agent-portal-design.md` (seções 3, 11, 12 ADR-001/002/003/005) + plano `2026-09-21-execution-plan.md` + decisão de arquitetura 6 containers (nginx, portal, orchestrator, agent-worker, postgres, minio).

## Objetivo

Levantar o ambiente local com `docker-compose up` subindo os 6 serviços (nginx, portal, orchestrator, agent-worker, postgres, minio) e um `.env.example` que documenta todas as variáveis. NGINX é o entry point único (porta 80), MinIO é o object storage para definições de agentes e skills, e o pool de agent-workers permite escala horizontal. É o chão que todos os outros domínios pisam.

## Escopo (o que FAZ)

- `docker-compose.yml` na raiz com 6 serviços: `nginx` (nginx:alpine, porta 80), `portal` (Next.js, porta 3000), `orchestrator` (FastAPI, porta 8000), `agent-worker` (FastAPI, porta 9000), `postgres` (pgvector/pgvector:pg15, porta 5432), `minio` (minio/minio, portas 9001/9002).
- `nginx/nginx.conf` com upstreams e regras de roteamento: `/` para portal, `/api/*` para orchestrator, `/workers/*` para pool de agent-workers (round-robin), WebSocket upgrade para `/api/ws`.
- `Dockerfile` do orchestrator (Python 3.11, uv/pip, alembic, healthcheck).
- `Dockerfile` do portal (Node 20, Next.js build, healthcheck).
- `Dockerfile` do agent-worker (Python 3.11-slim, FastAPI, httpx, pydantic, healthcheck em `/health`).
- Script de init do Postgres: cria a extensão `vector` e o DB `agent_portal`.
- Script de init do MinIO: cria os buckets `agents` e `skills`.
- Volume persistente `minio-data` para o MinIO.
- `.env.example` com todas as variáveis de ambiente, incluindo credenciais do MinIO.
- Estrutura de repositórios: `agent-portal/` (Next.js) + `agent-orchestrator/` (Python) + `agent-worker/` (Python) + `nginx/` + `docker-compose.yml` na raiz.

## Escopo (o que NÃO FAZ)

- NÃO implementa auth (D2), NÃO modela schema (D3), NÃO escreve endpoints funcionais.
- NÃO configura CI avançado (só deixa a estrutura pronta se fizer sentido).
- NÃO instala LangGraph, pgvector, nem frameworks de domínio — só o necessário pra subir os containers.
- NÃO cria secrets reais, só documenta onde entram.
- NÃO implementa a lógica de execução do agente (D4/D6), NÃO implementa a API do worker (D6 define o contrato HTTP).

## Dependências

- Nenhuma. É o primeiro domínio a rodar.

## Arquivos que OWNS

```
docker-compose.yml
nginx/
  nginx.conf
agent-portal/
  Dockerfile
  package.json
  tsconfig.json
  next.config.ts
  .env.example
agent-orchestrator/
  Dockerfile
  pyproject.toml
  alembic.ini
  .env.example
agent-worker/
  Dockerfile
  pyproject.toml
  .env.example
scripts/
  init-db.sql        (extensão vector + DB)
  init-minio.sh      (cria buckets agents e skills)
```

## Tarefas

### 1.1 Scaffold dos repositórios
- Criar `agent-portal/` com Next.js 14 (App Router), TypeScript, ESLint. `package.json` com `next`, `react`, `react-dom`, `typescript`, `@types/*`, `next-auth`, `axios`, `reactflow`. WebSocket nativo (browser API) não requer dependência externa.
- Criar `agent-orchestrator/` com FastAPI, `pyproject.toml` (uv), `alembic.ini`. Dependências: `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary` (ou `psycopg[binary]`), `alembic`, `python-jose` (JWT), `python-multipart`, `langgraph`, `langgraph-checkpoint-postgres`, `langchain-core`, `pydantic`, `python-json-logger`.
- Criar `agent-worker/` com FastAPI, `pyproject.toml` (uv). Dependências: `fastapi`, `uvicorn`, `httpx` (cliente S3 para MinIO), `pydantic`, `python-json-logger`. O worker é stateless e genérico: recebe `POST /execute` com `{agentId, inputs, capabilities}`, baixa o `.yml` do agente e os `.md` de skills do MinIO, executa e retorna JSON.
- Aceite: `npm install` no portal, `uv sync`/`pip install` no orchestrator e no agent-worker rodam sem erro.

### 1.2 Dockerfiles
- `agent-orchestrator/Dockerfile`: Python 3.11-slim, instala dependências, expõe 8000, healthcheck em `/health`.
- `agent-portal/Dockerfile`: Node 20, build estático ou server, expõe 3000, healthcheck em `/`.
- `agent-worker/Dockerfile`: Python 3.11-slim, instala dependências, expõe 9000, healthcheck em `/health`. Base mais leve que o orchestrator (sem alembic, sem langgraph).
- Aceite: `docker build` de todos os três termina sem erro.

### 1.3 docker-compose.yml
- 6 serviços:
  - `nginx` (nginx:alpine, porta 80, `depends_on` todos os demais, monta `nginx/nginx.conf`).
  - `portal` (build agent-portal, porta 3000).
  - `orchestrator` (build agent-orchestrator, porta 8000, `depends_on` postgres e minio com healthcheck).
  - `agent-worker` (build agent-worker, porta 9000, `depends_on` minio com healthcheck). Documentar uso de `--scale agent-worker=3` ou `deploy.replicas` para escala horizontal.
  - `postgres` (pgvector/pgvector:pg15, expõe 5432, volume `pgdata`).
  - `minio` (minio/minio, portas 9001 API e 9002 console, volume `minio-data`).
- `depends_on` com healthcheck: postgres e minio saudáveis antes de orchestrator e agent-worker. NGINX depende de todos.
- Rede compartilhada, variáveis de ambiente via `.env`.
- Aceite: `docker-compose up -d` sobe os 6 serviços.

### 1.4 Postgres init
- `scripts/init-db.sql`: `CREATE EXTENSION IF NOT EXISTS vector;` + `CREATE DATABASE agent_portal;` (ou via `POSTGRES_DB` no compose). A imagem `pgvector/pgvector:pg15` já inclui a extensão, então o `CREATE EXTENSION` funciona sem instalação adicional.
- Aceite: após `docker-compose up`, `docker exec postgres psql -c "SELECT extname FROM pg_extension;"` mostra `vector`.

### 1.5 .env.example
- Portal: `NEXTAUTH_SECRET`, `NEXTAUTH_URL`, `ORCHESTRATOR_API_URL`.
- Orchestrator: `DATABASE_URL` (aponta para o container `postgres` do compose, ex: `postgresql+psycopg://agent:agent@postgres:5432/agent_portal`), `JWT_SECRET`, `OPENAI_API_KEY`, `RIVVN_*`, `CORS_ORIGINS`.
- MinIO: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_ENDPOINT=http://minio:9001`, `MINIO_BUCKET_AGENTS=agents`, `MINIO_BUCKET_SKILLS=skills`.
- Agent-worker: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_ENDPOINT`, `MINIO_BUCKET_AGENTS`, `MINIO_BUCKET_SKILLS` (mesmas vars do MinIO, o worker precisa ler os objetos).
- Documentar cada var com comentário. Incluir comentário na `DATABASE_URL` indicando que a imagem do Postgres é `pgvector/pgvector:pg15` (já inclui a extensão vector).
- Aceite: `.env.example` cobre todas as vars usadas nos Dockerfiles e config.

### 1.6 nginx.conf
- `nginx/nginx.conf` com:
  - `upstream` blocks: `portal` (portal:3000), `orchestrator` (orchestrator:8000), `agent_workers` (agent-worker:9000, round-robin).
  - `location /` → proxy para `portal`.
  - `location /api/` → proxy para `orchestrator`.
  - `location /workers/` → proxy para `agent_workers` (round-robin).
  - `location /api/ws` → proxy para `orchestrator` com WebSocket upgrade (`Upgrade` e `Connection` headers).
  - `proxy_pass` com `proxy_set_header Host`, `X-Real-IP`, `X-Forwarded-For`.
- Aceite: `docker-compose up` → `curl http://localhost/` responde do portal, `curl http://localhost/api/health` responde do orchestrator.

### 1.7 Entrypoint do orchestrator
- O entrypoint do container do orchestrator roda `alembic upgrade head` antes de iniciar o servidor. Comando: `alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000`.
- Isso garante que as migrations estão aplicadas antes de qualquer request chegar.
- Aceite: ao subir o container, logs mostram as migrations sendo aplicadas e depois o servidor iniciando.

### 1.8 Logging
- Logging estruturado em JSON (usando `python-json-logger` ou `loguru`). Nível: INFO em produção, DEBUG em desenvolvimento. Formato: `{timestamp, level, message, pipeline_id?, agent_id?, run_id?}`. Logs vão para stdout (coletado pelo Docker). Aplica-se a orchestrator e agent-worker.
- Aceite: `docker logs orchestrator` e `docker logs agent-worker` mostram linhas JSON válidas com os campos acima.

### 1.9 MinIO bucket init
- `scripts/init-minio.sh`: usa `mc` (MinIO Client) para criar alias e buckets. Passos: `mc alias set local http://minio:9001 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD`, `mc mb --ignore-existing local/agents`, `mc mb --ignore-existing local/skills`.
- Rodar como `depends_on` do MinIO no compose (via `entrypoint` ou `init` container) ou documentar como passo manual pós-`docker-compose up`.
- Aceite: após init, `mc ls local/` mostra os buckets `agents` e `skills`.

### 1.10 Estrutura base de código
- Orchestrator: `app/main.py` mínimo (app FastAPI com rota `/health` que responde 200).
- Agent-worker: `main.py` mínimo (app FastAPI com rota `/health` que responde 200).
- Portal: `app/page.tsx` mínimo (página inicial renderiza "Agent Portal").
- Aceite: `docker-compose up` → `curl http://localhost/api/health` responde 200, `curl http://localhost/workers/health` responde 200, `curl http://localhost/` responde do portal.

## Critérios de aceite (DoD)

- [ ] `docker-compose up` sobe os 6 serviços sem erro
- [ ] NGINX responde em :80 e roteia corretamente (`/` para portal, `/api/` para orchestrator, `/workers/` para agent-worker)
- [ ] Postgres acessível com extensão `vector` ativa
- [ ] MinIO acessível em :9001 com buckets `agents` e `skills` criados
- [ ] FastAPI (orchestrator) responde em `/api/health`
- [ ] Agent-worker responde em `/workers/health`
- [ ] Next.js responde em `/`
- [ ] `.env.example` documenta todas as variáveis

## Contratos de interface (o que entrega aos outros)

- **Para D2:** estrutura do portal + orchestrator prontas, `.env.example` com `JWT_SECRET` e `NEXTAUTH_SECRET`, rota `/health` viva.
- **Para D3:** Postgres com extensão `vector`, `DATABASE_URL` documentada, estrutura de pastas para SQLAlchemy models.
- **Para D6:** NGINX roteia `/workers/execute` para o pool de agent-workers. O D6 chama `POST http://nginx:80/workers/execute` para delegar execução. O agent-worker expõe `/health` para healthcheck.
- **Para D4/D8:** MinIO disponível com buckets `agents` e `skills`. Credenciais via env (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_ENDPOINT`). S3 API compatível.
- **Para todos:** containers sobem com um comando, rede definida, variáveis documentadas, NGINX como entry point único.

## Riscos

- Imagem `pgvector/pgvector:pg15` resolve a compatibilidade entre pgvector e Postgres 15 sem instalação manual.
- Healthcheck do compose evita race condition postgres→orchestrator e minio→agent-worker.
- Entrypoint com `alembic upgrade head` pode falhar se o Postgres ainda não estiver pronto (mitigado pelo `depends_on` com healthcheck).
- Agent-worker stateless: se cair durante execução, o orchestrator detecta timeout e pode re-dispatch para outro worker. Checkpoint no Postgres garante retomada.
- MinIO single-instance na V1: volume persistente. Em V2, considerar MinIO distributed ou S3 real.
- NGINX round-robin sem health check: se um worker cai, o NGINX continua roteando até timeout. Mitigação: healthcheck no compose + retry no orchestrator.
