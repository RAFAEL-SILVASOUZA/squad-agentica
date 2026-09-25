# agent-orchestrator

Orquestrador de pipelines de agentes (FastAPI + LangGraph) do Agent Portal.

- **Porta interna:** `:8000` (não publicada; acessível via NGINX `/api/*`).
- **Health:** `GET /health` (container) e `GET /api/health` (via NGINX).
- **Descoberta de routers:** `app/main.py` inclui automaticamente todo módulo em
  `app/api/` que exponha `router = APIRouter(...)` (contrato §3). Nós paralelos
  só criam o próprio arquivo em `app/api/<dominio>.py`.

## Estrutura (scaffold, dono: infra-docker)

```
app/
  main.py            # FastAPI + descoberta de routers
  core/              # config, security, errors, llm, embeddings
  db/                # session.py, seed.py (skeleton; db-models/db-seed preenchem)
  api/               # um router por recurso (registro automático)
tests/               # health + descoberta de routers
alembic/             # env.py + versions/ (skeleton; db-migrations preenche)
```

## Rodar (dev, via compose)

```bash
docker compose up -d orchestrator
docker compose logs -f orchestrator
```

## Testes (dentro do container, contrato §4)

```bash
docker compose run --rm orchestrator pytest
```
