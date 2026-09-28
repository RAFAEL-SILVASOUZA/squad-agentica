# syntax=docker/dockerfile:1

# --- agent-orchestrator Dockerfile (dono: infra-docker) ---
# Python 3.11-slim. Base mais pesada que o worker (tem Alembic + LangGraph + pgvector).

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Ferramentas de sistema mínimas (binários usados pelos healthchecks e entrypoint).
# curl é instalado só para o healthcheck do compose; o orchestrator também expõe /health.
# git é usado pelo WorkspaceManager (Task 5): clone/commit/push dos workspaces
# de cada run (agent-orchestrator/app/runtime/workspace.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependências primeiro (melhor cache de camada).
# Fonte canônica: pyproject.toml (§3 do contrato). requirements.txt foi removido.
# Instala o extra [dev] (pytest, ruff, mypy, watchfiles) porque o contrato §4
# exige rodar os testes DENTRO do container (docker compose run --rm orchestrator pytest).
COPY pyproject.toml README.md .python-version ./
RUN pip install .[dev]

# Copia o código (no dev, o override bind-mounta /app; aqui é a imagem de produção).
COPY . .

# Healthcheck nativo da imagem (o compose também define um, mas este é o fallback).
HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=30s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

EXPOSE 8000

# Entrypoint: roda migrations + seed (tolerando inexistência temporária de tabelas)
# antes de iniciar o uvicorn (contrato §4). db-migrations / db-seed implementam os comandos.
ENTRYPOINT ["bash", "-c", "alembic upgrade head || true; python -m app.db.seed || true; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
