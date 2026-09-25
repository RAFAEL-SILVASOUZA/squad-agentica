"""Alembic environment (dono: db-migrations).

Lê a URL do banco de ``app.core.config`` (asyncpg) e importa o ``Base.metadata``
para autogeração. O nó db-migrations preenche a migration inicial.

Decisões (registradas para o revisor db-review):
- ``compare_type=True``: compara tipos de coluna (ex.: ``vector(1536)`` vs
  ``vector``) para que ``alembic check``/autogenerate detectem divergências.
- ``include_object`` ignora as tabelas de checkpoint do LangGraph
  (``checkpoints``/``checkpoint_writes``/``checkpoint_blobs``/
  ``checkpoint_migrations``), criadas pelo ``PostgresSaver.setup()`` no mesmo
  banco. Sem isso, todo autogenerate futuro tentaria apagá-las (não são nossas).
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.db import models  # noqa: F401
from app.db.session import Base  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Injeta a URL real (asyncpg) do ambiente.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# Tabelas criadas pelo LangGraph PostgresSaver.setup() no MESMO banco.
# Não fazem parte do nosso schema (não estão em Base.metadata); o autogenerate
# deve ignorá-las para não tentar apagá-las em uma migration futura.
_LANGGRAPH_TABLES = frozenset(
    {"checkpoints", "checkpoint_writes", "checkpoint_blobs", "checkpoint_migrations"}
)

# Índice HNSW criado via op.execute() na migration (D3 §3.2). Não está em
# Base.metadata (o model não declara índice); o autogenerate precisa ignorá-lo
# para não detectar "remove_index" em `alembic check`.
_HNSW_INDEX = "idx_chunks_embedding_hnsw"


def include_object(object_, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    """Exclui objetos não-modelados do conjunto comparado pelo autogenerate.

    - Tabelas do LangGraph (criadas pelo PostgresSaver.setup()).
    - Índice HNSW (criado via op.execute, não declarado no model).
    """
    if type_ == "table" and name in _LANGGRAPH_TABLES:
        return False
    if type_ == "index" and name == _HNSW_INDEX:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
