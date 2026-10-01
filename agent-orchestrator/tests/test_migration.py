"""Testes da migration inicial (db-migrations, FASE 2).

Cobrem o PLANO-BACKEND §2.6 (critérios de aceite):
(a) drop do schema, ``alembic upgrade head``, comparação via ``MetaData`` dos
    models → tabelas equivalentes (a migration reflete os models);
(b) ``knowledge_chunks.embedding`` permanece ``vector(1536)`` após a migration;
(c) índice HNSW ``idx_chunks_embedding_hnsw`` existe após a migration (D3 §3.2);
(d) ``alembic check`` não detecta novas operações (schema == models).

Banco de teste isolado (fixture ``test_engine`` do conftest). A migration roda
via subprocess ``alembic`` apontando para o banco de teste (``DATABASE_URL``
sobrescrito), nunca o banco ``agent_portal`` de desenvolvimento.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest_asyncio
from sqlalchemy import inspect, text

from app.db.session import Base

# Diretório do projeto (agent-orchestrator), onde vivem alembic.ini e alembic/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Tabelas que a migration deve criar (as 17 da spec §4 + alembic_version).
EXPECTED_TABLES = {
    "users",
    "agents",
    "pipelines",
    "pipeline_nodes",
    "pipeline_edges",
    "pipeline_runs",
    "run_checkpoints",
    "skills",
    "custom_tools",
    "mcp_servers",
    "knowledge_bases",
    "knowledge_documents",
    "knowledge_chunks",
    "knowledge_conversations",
    "knowledge_messages",
    "approval_requests",
    "artifacts",
    "integrations",
    "rivvn_connections",
    "mcp_oauth_clients",
    "mcp_oauth_tokens",
    "alembic_version",
}


def _test_db_url(test_engine) -> str:
    """URL do banco de teste (a mesma usada pela fixture test_engine).

    Constrói o URL a partir de ``settings.database_url`` (que tem a senha
    correta) e substitui o nome do banco pelo do banco de teste. Isso evita
    problemas de parsing/masking ao usar ``test_engine.url`` diretamente.
    """
    from urllib.parse import urlparse, urlunparse

    from app.core.config import settings

    # Extrai o nome do banco de teste do URL do engine.
    engine_url = str(test_engine.url)
    parsed_engine = urlparse(engine_url)
    db_name = parsed_engine.path.lstrip("/")

    # Constrói o URL a partir de settings.database_url (senha correta).
    parsed_settings = urlparse(settings.database_url)
    return urlunparse(parsed_settings._replace(path=f"/{db_name}"))


def _run_alembic(test_engine, *args: str) -> subprocess.CompletedProcess:
    """Roda ``alembic`` com DATABASE_URL apontando para o banco de teste."""
    url = _test_db_url(test_engine)
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        ["alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest_asyncio.fixture
async def migrated_engine(test_engine):
    """Roda ``alembic upgrade head`` no banco de teste e devolve o engine.

    O banco de teste já tem o schema via ``create_all`` (fixture test_engine);
    para testar a migration de verdade, derrubamos o schema e aplicamos a
    migration do zero.
    """
    # Drop do schema criado pelo create_all (para a migration criar do zero).
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # Aplica a migration inicial.
    result = _run_alembic(test_engine, "upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade head falhou:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    yield test_engine


async def test_migration_creates_all_tables(migrated_engine) -> None:
    """(a) alembic upgrade head cria todas as tabelas dos models."""
    async with migrated_engine.connect() as conn:
        tables = await conn.run_sync(lambda sc: inspect(sc).get_table_names())
    assert EXPECTED_TABLES <= set(tables), f"Faltam tabelas: {EXPECTED_TABLES - set(tables)}"


async def test_migration_embedding_is_vector_1536(migrated_engine) -> None:
    """(b) knowledge_chunks.embedding permanece vector(1536) após a migration.

    Consulta o ``pg_attribute``/``information_schema`` diretamente, pois o
    tipo ``vector`` é custom (pgvector) e o inspector do SQLAlchemy retorna
    ``NULL`` para tipos desconhecidos.
    """
    async with migrated_engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT a.attname, t.typname, a.atttypmod "
                "FROM pg_attribute a "
                "JOIN pg_class c ON a.attrelid = c.oid "
                "JOIN pg_type t ON a.atttypid = t.oid "
                "WHERE c.relname='knowledge_chunks' AND a.attname='embedding'"
            )
        )
        result = row.fetchone()
    assert result is not None, "Coluna embedding não encontrada"
    attname, typname, atttypmod = result
    assert typname == "vector", f"embedding não é vector: {typname}"
    # O pgvector armazena a dimensão diretamente em atttypmod (sem offset).
    dim = atttypmod if atttypmod > 0 else None
    assert dim == 1536, f"embedding não é vector(1536): dim={dim}"


async def test_migration_hnsw_index_exists(migrated_engine) -> None:
    """(c) índice HNSW idx_chunks_embedding_hnsw existe após a migration."""
    async with migrated_engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename='knowledge_chunks' "
                "AND indexname='idx_chunks_embedding_hnsw'"
            )
        )
        result = row.fetchone()
    assert result is not None, "Índice HNSW idx_chunks_embedding_hnsw não encontrado"
    indexdef = result[0].lower()
    assert "hnsw" in indexdef, f"Índice não é HNSW: {indexdef}"
    assert "vector_cosine_ops" in indexdef, f"Índice não usa vector_cosine_ops: {indexdef}"


async def test_migration_vector_extension(migrated_engine) -> None:
    """A extensão vector está habilitada após a migration."""
    async with migrated_engine.connect() as conn:
        row = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        )
        result = row.fetchone()
    assert result is not None, "Extensão vector não habilitada após a migration"


async def test_migration_matches_models_metadata(migrated_engine) -> None:
    """(a) A migration reflete os models: comparação via MetaData.

    Compara as tabelas criadas pela migration com ``Base.metadata``:
    mesmas tabelas, mesmas colunas (nome + nullability) por tabela.

    Usa reflexão direta (``inspect``) em vez de ``alembic.autogenerate``
    (que tem problemas de import no contexto de teste devido ao shadowing
    do pacote local ``alembic/``).
    """
    # Tabelas esperadas (as 17 da spec §4, sem alembic_version).
    expected_tables = set(Base.metadata.tables.keys())

    async with migrated_engine.connect() as conn:
        # Reflete as tabelas do banco.
        reflected_tables = await conn.run_sync(lambda sc: inspect(sc).get_table_names())
        # Para cada tabela esperada, compara as colunas.
        for table_name in expected_tables:
            assert table_name in reflected_tables, (
                f"Tabela {table_name} não criada pela migration"
            )
            # Compara as colunas (nome + nullability).
            reflected_cols = await conn.run_sync(
                lambda sc, tn=table_name: {
                    c["name"]: c["nullable"] for c in inspect(sc).get_columns(tn)
                }
            )
            model_table = Base.metadata.tables[table_name]
            model_cols = {
                col.name: col.nullable for col in model_table.columns
            }
            # As colunas devem corresponder (nome + nullability).
            assert reflected_cols == model_cols, (
                f"Colunas de {table_name} divergem:\n"
                f"  refletidas: {reflected_cols}\n"
                f"  models:     {model_cols}"
            )


async def test_alembic_check_no_diff(migrated_engine) -> None:
    """(d) alembic check não detecta novas operações (schema == models)."""
    result = _run_alembic(migrated_engine, "check")
    assert result.returncode == 0, (
        f"alembic check detectou diferenças:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
