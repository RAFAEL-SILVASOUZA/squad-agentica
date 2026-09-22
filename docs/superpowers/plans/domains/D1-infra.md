# D1 — Infraestrutura & Setup

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 1 · Fundação**. Dependência: nenhuma.
> Base: spec `2026-09-17-agent-portal-design.md` (seções 3, 11, 12 ADR-001/002/003/005) + plano `2026-09-21-execution-plan.md`.

## Objetivo

Levantar o ambiente local com `docker-compose up` subindo os 3 serviços (portal, orchestrator, postgres) e um `.env.example` que documenta todas as variáveis. É o chão que todos os outros domínios pisam.

## Escopo (o que FAZ)

- `docker-compose.yml` na raiz com 3 serviços: `portal` (Next.js), `orchestrator` (FastAPI), `postgres` (pgvector/pgvector:pg15).
- `Dockerfile` do orchestrator (Python 3.11, uv/pip, alembic, healthcheck).
- `Dockerfile` do portal (Node 20, Next.js build, healthcheck).
- Script de init do Postgres: cria a extensão `vector` e o DB `agent_portal`.
- `.env.example` com todas as variáveis de ambiente.
- Estrutura de repositórios: `agent-portal/` (Next.js) + `agent-orchestrator/` (Python) + `docker-compose.yml` na raiz.

## Escopo (o que NÃO FAZ)

- NÃO implementa auth (D2), NÃO modela schema (D3), NÃO escreve endpoints funcionais.
- NÃO configura CI avançado (só deixa a estrutura pronta se fizer sentido).
- NÃO instala LangGraph, pgvector, nem frameworks de domínio — só o necessário pra subir os containers.
- NÃO cria secrets reais, só documenta onde entram.

## Dependências

- Nenhuma. É o primeiro domínio a rodar.

## Arquivos que OWNS

```
docker-compose.yml
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
scripts/init-db.sql        (extensão vector + DB)
```

## Tarefas

### 1.1 Scaffold dos repositórios
- Criar `agent-portal/` com Next.js 14 (App Router), TypeScript, ESLint. `package.json` com `next`, `react`, `react-dom`, `typescript`, `@types/*`, `next-auth`, `axios`, `reactflow`. WebSocket nativo (browser API) não requer dependência externa.
- Criar `agent-orchestrator/` com FastAPI, `pyproject.toml` (uv), `alembic.ini`. Dependências: `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary` (ou `psycopg[binary]`), `alembic`, `python-jose` (JWT), `python-multipart`, `langgraph`, `langgraph-checkpoint-postgres`, `langchain-core`, `pydantic`, `python-json-logger`.
- Aceite: `npm install` no portal e `uv sync`/`pip install` no orchestrator rodam sem erro.

### 1.2 Dockerfiles
- `agent-orchestrator/Dockerfile`: Python 3.11-slim, instala dependências, expõe 8000, healthcheck em `/health`.
- `agent-portal/Dockerfile`: Node 20, build estático ou server, expõe 3000, healthcheck em `/`.
- Aceite: `docker build` de ambos termina sem erro.

### 1.3 docker-compose.yml
- 3 serviços: `portal` (build agent-portal, porta 3000), `orchestrator` (build agent-orchestrator, porta 8000), `postgres` (pgvector/pgvector:pg15, expõe 5432, volume pgdata).
- `depends_on` com healthcheck (postgres saudável antes de orchestrator).
- Rede compartilhada, variáveis de ambiente via `.env`.
- Aceite: `docker-compose up -d` sobe os 3 serviços.

### 1.4 Postgres init
- `scripts/init-db.sql`: `CREATE EXTENSION IF NOT EXISTS vector;` + `CREATE DATABASE agent_portal;` (ou via `POSTGRES_DB` no compose). A imagem `pgvector/pgvector:pg15` já inclui a extensão, então o `CREATE EXTENSION` funciona sem instalação adicional.
- Aceite: após `docker-compose up`, `docker exec postgres psql -c "SELECT extname FROM pg_extension;"` mostra `vector`.

### 1.5 .env.example
- Portal: `NEXTAUTH_SECRET`, `NEXTAUTH_URL`, `ORCHESTRATOR_API_URL`.
- Orchestrator: `DATABASE_URL` (aponta para o container `postgres` do compose, ex: `postgresql+psycopg://agent:agent@postgres:5432/agent_portal`), `JWT_SECRET`, `OPENAI_API_KEY`, `RIVVN_*`, `CORS_ORIGINS`.
- Documentar cada var com comentário. Incluir comentário na `DATABASE_URL` indicando que a imagem do Postgres é `pgvector/pgvector:pg15` (já inclui a extensão vector).
- Aceite: `.env.example` cobre todas as vars usadas nos Dockerfiles e config.

### 1.7 Entrypoint do orchestrator
- O entrypoint do container do orchestrator roda `alembic upgrade head` antes de iniciar o servidor. Comando: `alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000`.
- Isso garante que as migrations estão aplicadas antes de qualquer request chegar.
- Aceite: ao subir o container, logs mostram as migrations sendo aplicadas e depois o servidor iniciando.

### 1.8 Logging
- Logging estruturado em JSON (usando `python-json-logger` ou `loguru`). Nível: INFO em produção, DEBUG em desenvolvimento. Formato: `{timestamp, level, message, pipeline_id?, agent_id?, run_id?}`. Logs vão para stdout (coletado pelo Docker).
- Aceite: `docker logs orchestrator` mostra linhas JSON válidas com os campos acima.

### 1.6 Estrutura base de código
- Orchestrator: `app/main.py` mínimo (app FastAPI com rota `/health` que responde 200).
- Portal: `app/page.tsx` mínimo (página inicial renderiza "Agent Portal").
- Aceite: `docker-compose up` → `/health` responde 200 no orchestrator, `/` responde no portal.

## Critérios de aceite (DoD)

- [ ] `docker-compose up` sobe os 3 serviços sem erro
- [ ] Postgres acessível com extensão `vector` ativa
- [ ] FastAPI responde em `/health`
- [ ] Next.js responde em `/`
- [ ] `.env.example` documenta todas as variáveis

## Contratos de interface (o que entrega aos outros)

- **Para D2:** estrutura do portal + orchestrator prontas, `.env.example` com `JWT_SECRET` e `NEXTAUTH_SECRET`, rota `/health` viva.
- **Para D3:** Postgres com extensão `vector`, `DATABASE_URL` documentada, estrutura de pastas para SQLAlchemy models.
- **Para todos:** containers sobem com um comando, rede definida, variáveis documentadas.

## Riscos

- Imagem `pgvector/pgvector:pg15` resolve a compatibilidade entre pgvector e Postgres 15 sem instalação manual.
- Healthcheck do compose evita race condition postgres→orchestrator.
- Entrypoint com `alembic upgrade head` pode falhar se o Postgres ainda não estiver pronto (mitigado pelo `depends_on` com healthcheck).
