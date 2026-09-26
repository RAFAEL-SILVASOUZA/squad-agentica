"""Checkpoint persistence via AsyncPostgresSaver (langgraph-checkpoint-postgres).

Factory function that the executor (rt-executor) calls at startup to obtain
a configured AsyncPostgresSaver instance. The saver is passed by injection
into compile_pipeline() (ADR-004: PostgresSaver por injeção, não string).

thread_id convention (D6-runtime.md §6.2):
    f'{pipelineId}:{runId}'
This isolates checkpoints of different executions of the same pipeline.

Usage (executor startup):
    from app.runtime.checkpoint import create_checkpointer

    checkpointer = await create_checkpointer(database_url)
    # ... later, pass to compile_pipeline:
    graph = compile_pipeline(pipeline, worker_client=wc, checkpointer=checkpointer)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)


def _to_psycopg_url(database_url: str) -> str:
    """Convert a SQLAlchemy URL to a plain psycopg URL.

    psycopg does not understand the ``+asyncpg`` driver suffix that
    SQLAlchemy uses.  ``postgresql+asyncpg://user:pass@host:5432/db``
    becomes ``postgresql://user:pass@host:5432/db``.
    """
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_checkpointer(database_url: str) -> AsyncPostgresSaver:
    """Create and initialize an AsyncPostgresSaver.

    Connects to the given PostgreSQL database, creates the checkpoint tables
    via setup() (idempotent: safe to call on every startup), and returns
    the ready-to-use saver.

    Args:
        database_url: PostgreSQL connection string. Accepts both the plain
            psycopg format (``postgresql://user:pass@host:5432/db``) and the
            SQLAlchemy format (``postgresql+asyncpg://user:pass@host:5432/db``).

    Returns:
        An AsyncPostgresSaver with tables created. The caller is responsible
        for closing the underlying connection (use close_checkpointer).

    Raises:
        psycopg.OperationalError: if the database is unreachable.
    """
    conn = await psycopg.AsyncConnection.connect(
        _to_psycopg_url(database_url),
        autocommit=True,
        row_factory=psycopg.rows.dict_row,
    )
    saver = AsyncPostgresSaver(conn)
    await saver.setup()
    logger.info("Checkpointer initialized (tables ready)")
    return saver


async def close_checkpointer(checkpointer: AsyncPostgresSaver) -> None:
    """Close the underlying connection of a checkpointer.

    Call this at application shutdown to release the connection.
    """
    conn = checkpointer.conn
    if conn is not None and not conn.closed:
        await conn.close()
        logger.info("Checkpointer connection closed")


@asynccontextmanager
async def checkpointer_context(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    """Context manager that creates and closes a checkpointer.

    Usage:
        async with checkpointer_context(url) as cp:
            graph = compile_pipeline(..., checkpointer=cp)
    """
    cp = await create_checkpointer(database_url)
    try:
        yield cp
    finally:
        await close_checkpointer(cp)


def make_thread_id(pipeline_id: str, run_id: str) -> str:
    """Build the thread_id for a pipeline execution.

    Convention (D6-runtime.md §6.2): f'{pipelineId}:{runId}'.
    This isolates checkpoints of different runs of the same pipeline.

    Args:
        pipeline_id: UUID of the pipeline.
        run_id: UUID of this specific execution.

    Returns:
        The thread_id string to use in the LangGraph config.
    """
    return f"{pipeline_id}:{run_id}"
