"""Tests for app/runtime/checkpoint.py.

Covers:
  - create_checkpointer creates tables and returns a working saver
  - Checkpoint saves and retrieves state of a minimal graph
  - thread_id convention (pipelineId:runId)
  - close_checkpointer closes the connection
  - checkpointer_context context manager

Uses the test database from conftest.py (isolated, per CONTRATO-TECNICO.md §4).
"""

import uuid

import asyncpg
import pytest
import pytest_asyncio

from app.core.config import settings

pytestmark = pytest.mark.asyncio


def _psycopg_url(url: str) -> str:
    """Convert postgresql+asyncpg:// to postgresql:// for psycopg driver."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest_asyncio.fixture(scope="module")
async def test_db_url(test_database_url: str):
    """Create the test database and provide its psycopg URL.

    Uses the test_database_url from conftest (unique per session).
    Creates the actual database if it doesn't exist.
    """
    # Create the database (connect to the main DB to issue CREATE DATABASE).
    admin_url = _psycopg_url(settings.database_url)
    db_name = test_database_url.rsplit("/", 1)[-1]
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    except asyncpg.InvalidCatalogNameError:
        pass  # Already exists (shouldn't happen with UUID suffix).
    finally:
        await conn.close()

    yield _psycopg_url(test_database_url)

    # Teardown: drop the test database.
    conn = await asyncpg.connect(admin_url)
    await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    await conn.close()


@pytest_asyncio.fixture
async def checkpointer(test_db_url: str):
    """Create a checkpointer for each test (isolated thread_ids)."""
    from app.runtime.checkpoint import close_checkpointer, create_checkpointer

    cp = await create_checkpointer(test_db_url)
    yield cp
    await close_checkpointer(cp)


class TestCreateCheckpointer:
    """Tests for the create_checkpointer factory."""

    async def test_creates_saver_with_tables(self, test_db_url):
        """create_checkpointer returns an AsyncPostgresSaver with tables ready."""
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from app.runtime.checkpoint import close_checkpointer, create_checkpointer

        cp = await create_checkpointer(test_db_url)
        assert isinstance(cp, AsyncPostgresSaver)
        await close_checkpointer(cp)

    async def test_idempotent_setup(self, test_db_url):
        """Calling create_checkpointer twice on the same DB doesn't fail."""
        from app.runtime.checkpoint import close_checkpointer, create_checkpointer

        cp1 = await create_checkpointer(test_db_url)
        await close_checkpointer(cp1)

        cp2 = await create_checkpointer(test_db_url)
        assert cp2 is not None
        await close_checkpointer(cp2)


class TestThreadID:
    """Tests for the thread_id convention."""

    async def test_make_thread_id_format(self):
        """thread_id is f'{pipelineId}:{runId}' (D6-runtime.md §6.2)."""
        from app.runtime.checkpoint import make_thread_id

        pipeline_id = "abc-123"
        run_id = "def-456"
        result = make_thread_id(pipeline_id, run_id)
        assert result == "abc-123:def-456"

    async def test_make_thread_id_unique_per_run(self):
        """Different run_ids produce different thread_ids."""
        from app.runtime.checkpoint import make_thread_id

        tid1 = make_thread_id("pipeline-1", "run-1")
        tid2 = make_thread_id("pipeline-1", "run-2")
        assert tid1 != tid2


class TestCheckpointSaveAndRetrieve:
    """Tests for saving and retrieving checkpoint state."""

    async def test_save_and_retrieve_minimal_graph(self, checkpointer):
        """Checkpoint saves and retrieves state of a minimal graph.

        Uses a simple 2-node graph (A -> B) to verify the full
        save/retrieve cycle works with the test database.
        """
        from langgraph.graph import END, START, StateGraph

        from app.compiler.state import State, initial_state
        from app.runtime.checkpoint import make_thread_id

        # Build a minimal graph: A -> B.
        # Note: no type annotations on node functions to avoid
        # get_type_hints issues with from __future__ import annotations.
        def node_a(state):
            return {"data": {"a": {"result": "from_a"}}, "status": {"a": "completed"}}

        def node_b(state):
            return {"data": {"b": {"result": "from_b"}}, "status": {"b": "completed"}}

        graph = StateGraph(State)
        graph.add_node("a", node_a)
        graph.add_node("b", node_b)
        graph.add_edge(START, "a")
        graph.add_edge("a", "b")
        graph.add_edge("b", END)

        compiled = graph.compile(checkpointer=checkpointer)

        # Execute the graph with a unique thread_id.
        thread_id = make_thread_id("test-pipeline", f"run-{uuid.uuid4().hex[:8]}")
        config = {"configurable": {"thread_id": thread_id}}

        result = await compiled.ainvoke(initial_state(), config)

        # Verify the result is correct.
        assert result["data"]["a"]["result"] == "from_a"
        assert result["data"]["b"]["result"] == "from_b"
        assert result["status"]["a"] == "completed"
        assert result["status"]["b"] == "completed"

        # Verify checkpoint was saved: retrieve it.
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        assert checkpoint_tuple is not None
        assert checkpoint_tuple.config["configurable"]["thread_id"] == thread_id

    async def test_checkpoint_survives_new_saver_instance(self, test_db_url):
        """ADR-004: checkpoint survives process restart (new saver instance).

        Simulates: process 1 saves checkpoint, process 2 (new saver) reads it.
        """
        from langgraph.graph import END, START, StateGraph

        from app.compiler.state import State, initial_state
        from app.runtime.checkpoint import (
            close_checkpointer,
            create_checkpointer,
            make_thread_id,
        )

        def node_a(state):
            return {"data": {"a": {"value": 42}}, "status": {"a": "completed"}}

        graph = StateGraph(State)
        graph.add_node("a", node_a)
        graph.add_edge(START, "a")
        graph.add_edge("a", END)

        thread_id = make_thread_id("test-pipeline", f"restart-{uuid.uuid4().hex[:8]}")
        config = {"configurable": {"thread_id": thread_id}}

        # Process 1: save checkpoint.
        cp1 = await create_checkpointer(test_db_url)
        compiled1 = graph.compile(checkpointer=cp1)
        await compiled1.ainvoke(initial_state(), config)
        await close_checkpointer(cp1)

        # Process 2: new saver, retrieve checkpoint.
        cp2 = await create_checkpointer(test_db_url)
        checkpoint_tuple = await cp2.aget_tuple(config)
        assert checkpoint_tuple is not None
        # The checkpoint data should contain the state from process 1.
        assert checkpoint_tuple.checkpoint is not None
        await close_checkpointer(cp2)


class TestCloseCheckpointer:
    """Tests for close_checkpointer."""

    async def test_close_checkpointer_closes_connection(self, test_db_url):
        """close_checkpointer closes the underlying connection."""
        from app.runtime.checkpoint import close_checkpointer, create_checkpointer

        cp = await create_checkpointer(test_db_url)
        conn = cp.conn
        assert conn is not None
        assert not conn.closed

        await close_checkpointer(cp)
        assert conn.closed

    async def test_close_checkpointer_idempotent(self, test_db_url):
        """Calling close_checkpointer twice doesn't raise."""
        from app.runtime.checkpoint import close_checkpointer, create_checkpointer

        cp = await create_checkpointer(test_db_url)
        await close_checkpointer(cp)
        # Second call should not raise.
        await close_checkpointer(cp)


class TestCheckpointerContext:
    """Tests for the checkpointer_context context manager."""

    async def test_context_manager_yields_and_closes(self, test_db_url):
        """checkpointer_context yields a working saver and closes on exit."""
        from app.runtime.checkpoint import checkpointer_context

        async with checkpointer_context(test_db_url) as cp:
            assert cp is not None
            conn = cp.conn
            assert conn is not None
            assert not conn.closed

        # After context exit, connection should be closed.
        assert conn.closed
