# syntax=docker/dockerfile:1

# --- agent-worker Dockerfile (dono: infra-docker) ---
# Python 3.11-slim. Base mais leve que o orchestrator (sem Alembic, sem LangGraph).
# O worker executa um agente por request: baixa .yml/.md do MinIO, roda o agente, devolve output.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# wget é leve e nativo das imagens alpine/slim; usado pelo healthcheck do compose.
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependências primeiro (melhor cache de camada).
# Fonte canônica: pyproject.toml (§3 do contrato).
# Instala o extra [dev] (pytest, ruff, mypy, watchfiles) porque o contrato §4
# exige rodar os testes DENTRO do container (docker compose run --rm agent-worker pytest).
COPY pyproject.toml README.md .python-version ./
RUN pip install .[dev]

# Copia o código (no dev, o override bind-mounta /app; aqui é a imagem de produção).
COPY . .

# Healthcheck nativo da imagem (o compose também define um, mas este é o fallback).
HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:9000/health').status==200 else 1)"

EXPOSE 9000

# Entrypoint: só o uvicorn (o worker não roda migrations/seed — os checkpoints são do orchestrator).
ENTRYPOINT ["bash", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 9000"]
