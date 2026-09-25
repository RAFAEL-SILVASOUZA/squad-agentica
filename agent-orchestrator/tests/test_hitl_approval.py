"""Tests for app/approvals/ (node_function, service, api).

Cobrem (por requisito do prompt):
  - Nó sem efeitos antes do interrupt (reexecução não cria duplicata).
  - Upsert idempotente.
  - Respond nos três modos (aprovar, rejeitar, argumentar).
  - Dupla resposta (409).
  - Isolamento por owner.

Usa MemorySaver (sem DB real) para o nó e o banco de teste isolado (conftest)
para o service e a API.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.node_function import HUMAN_FEEDBACK_KEY
from app.compiler.graph_builder import (
    AgentSnapshot,
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PortDef,
    WorkerResponse,
    compile_pipeline,
)
from app.compiler.state import initial_state
from app.db.models import ApprovalRequest, User
from app.db.models import Pipeline as PipelineModel
from app.db.session import get_db

# ---------------------------------------------------------------------------
# FakeWorker (mesmo padrão dos testes do executor)
# ---------------------------------------------------------------------------


class FakeWorker:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        agent_id: str,
        node_id: str,
        inputs: dict[str, Any],
        *,
        timeout: int = 60,
    ) -> WorkerResponse:
        self.calls.append({"agent_id": agent_id, "node_id": node_id, "inputs": inputs})
        outputs = {k: f"{agent_id}:{v}" for k, v in inputs.items()}
        if not outputs:
            outputs["result"] = f"{agent_id}:done"
        return WorkerResponse(status="completed", outputs=outputs, action="follow", iterations=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(node_id: str, agent_id: str, **kw) -> PipelineNode:
    return PipelineNode(
        id=node_id,
        agent_id=agent_id,
        agent_snapshot=AgentSnapshot(
            agent_id=agent_id,
            name=agent_id,
            inputs=kw.pop("inputs", []),
            outputs=kw.pop("outputs", []),
            actions=kw.pop("actions", ["follow"]),
            max_iterations=kw.pop("max_iterations", 10),
            timeout=30,
        ),
    )


def _edge(edge_id: str, source: str, target: str, **kw) -> PipelineEdge:
    return PipelineEdge(
        id=edge_id,
        type=kw.pop("type", "flow"),
        source=source,
        target=target,
        condition=kw.pop("condition", None),
        requires_approval=kw.pop("requires_approval", False),
        data_mapping=kw.pop("data_mapping", None),
        reject_target=kw.pop("reject_target", None),
        approval_message=kw.pop("approval_message", None),
        approval_channel=kw.pop("approval_channel", None),
    )


def _approval_pipeline() -> Pipeline:
    """A -> [aprovação] -> B."""
    return Pipeline(
        id="p-approval",
        name="approval-test",
        entry_node_id="A",
        nodes=[
            _node("A", "agent-a", outputs=[PortDef(name="out", type="string")]),
            _node("B", "agent-b", inputs=[PortDef(name="in", type="string")]),
        ],
        edges=[
            _edge(
                "e1",
                "A",
                "B",
                requires_approval=True,
                approval_message="Aprovar saída de A?",
                reject_target="A",
            ),
        ],
    )


async def _create_user(session: AsyncSession, email: str | None = None) -> User:
    """Cria um usuário real no banco (owner_id = id do próprio user)."""
    user = User(
        id=uuid.uuid4(),
        email=email or f"user-{uuid.uuid4().hex[:8]}@test.com",
        name="Test User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _make_client(session: AsyncSession, user: User) -> Any:
    """Cria um client FastAPI com sessão de teste e user autenticado."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.approvals import router as approvals_router
    from app.auth.dependencies import get_current_user
    from app.core.errors import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(approvals_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _make_pipeline(owner_id: uuid.UUID) -> PipelineModel:
    return PipelineModel(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name="test-pipeline",
        entry_node_id=uuid.uuid4(),
    )


def _make_approval(
    owner_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    status: str = "pending",
    run_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        id=uuid.uuid4(),
        owner_id=owner_id,
        pipeline_id=pipeline_id,
        run_id=run_id,
        node_id="approval_node_e1",
        checkpoint_id="task-id-1",
        message="Aprovar?",
        context={},
        status=status,
        channel="in-app",
    )


@pytest.fixture
def worker() -> FakeWorker:
    return FakeWorker()


@pytest.fixture
def saver() -> MemorySaver:
    return MemorySaver()


# ---------------------------------------------------------------------------
# Teste 1: Nó sem efeitos colaterais antes do interrupt
# ---------------------------------------------------------------------------


class TestNoSideEffectsBeforeInterrupt:
    """O nó de aprovação NÃO tem efeitos colaterais antes do interrupt().

    ADR-009: a persistência da ApprovalRequest e a notificação são feitas pelo
    executor (hook), não pelo nó. O nó só monta o payload (puro) e chama
    interrupt(). Ao retomar, o nó re-executa do início; como não há efeitos
    colaterais antes do interrupt, nada se duplica.
    """

    async def test_no_side_effects_before_interrupt(
        self, worker: FakeWorker, saver: MemorySaver
    ):
        """O nó não persiste nem notifica antes do interrupt.

        Verifica: ao pausar (primeira execução), nenhum efeito colateral
        aconteceu (o nó só montou o payload e chamou interrupt). A
        ApprovalRequest é criada pelo hook do executor, não pelo nó.
        """
        pipeline = _approval_pipeline()
        graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)
        config = {"configurable": {"thread_id": "t1"}}
        state = initial_state()
        state["data"] = {"A": {"out": "hello"}}

        # Primeira execução: pausa no nó de aprovação.
        await graph.ainvoke(state, config=config)

        snap = graph.get_state(config)
        assert snap is not None
        # O nó de aprovação está em "next" (aguardando resume).
        assert any("approval_node" in n for n in snap.next)

        # O nó de aprovação NÃO criou nenhum efeito colateral: o nó só montou
        # o payload e chamou interrupt. A persistência é do hook (testada
        # separadamente). Aqui verificamos que o nó não tocou em nada do State
        # além do que o agente A já escreveu. O agente A executou e escreveu
        # seu output (result); o nó de aprovação não escreveu nada além disso.
        assert snap.values["data"]["A"] == {"result": "agent-a:done"}
        # O nó de aprovação não escreveu nada no State antes do interrupt.
        assert "B" not in snap.values["data"]

    async def test_reexecution_does_not_duplicate(
        self, worker: FakeWorker, saver: MemorySaver
    ):
        """Reexecução do nó (ao retomar) não cria duplicata.

        O LangGraph re-executa o nó inteiro ao retomar. Como o nó não tem
        efeitos colaterais antes do interrupt, a reexecução é idempotente:
        o interrupt() retorna a resposta e o nó roteia, sem duplicar nada.
        """
        pipeline = _approval_pipeline()
        graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)
        config = {"configurable": {"thread_id": "t2"}}
        state = initial_state()
        state["data"] = {"A": {"out": "hello"}}

        # Pausa.
        await graph.ainvoke(state, config=config)
        snap = graph.get_state(config)
        assert snap is not None
        assert any("approval_node" in n for n in snap.next)

        # Retoma com "approved": o nó re-executa do início, o interrupt()
        # retorna "approved", e o nó roteia para B.
        await graph.ainvoke(Command(resume="approved"), config=config)

        snap = graph.get_state(config)
        assert snap is not None
        # B executou (o nó roteou para B após a reexecução).
        assert snap.values["status"]["B"] == "completed"
        # A executou uma vez (não duplicou).
        assert snap.values["iterations"]["A"] == 1
        # B executou uma vez.
        assert snap.values["iterations"]["B"] == 1


# ---------------------------------------------------------------------------
# Teste 2: Upsert idempotente (service)
# ---------------------------------------------------------------------------


class TestUpsertIdempotent:
    """O upsert da ApprovalRequest é idempotente por chave (ADR-009)."""

    async def test_upsert_creates_then_idempotent(self, session: AsyncSession):
        """Primeira chamada cria; segunda (mesma chave) não duplica."""
        from app.approvals.service import upsert_approval_request

        user = await _create_user(session)
        owner_id = user.owner_id
        pipeline_id = uuid.uuid4()
        run_id = uuid.uuid4()
        node_id = "approval_node_e1"
        interrupt_id = "task-id-123"
        payload = {"message": "Aprovar?", "context": {"out": "hello"}}

        # Primeira chamada: cria.
        approval1, created1 = await upsert_approval_request(
            session,
            owner_id=owner_id,
            pipeline_id=pipeline_id,
            run_id=run_id,
            node_id=node_id,
            interrupt_id=interrupt_id,
            payload=payload,
        )
        assert created1 is True
        assert approval1.status == "pending"
        assert approval1.message == "Aprovar?"
        assert approval1.context == {"out": "hello"}

        # Segunda chamada (mesma chave): idempotente, não duplica.
        approval2, created2 = await upsert_approval_request(
            session,
            owner_id=owner_id,
            pipeline_id=pipeline_id,
            run_id=run_id,
            node_id=node_id,
            interrupt_id=interrupt_id,
            payload=payload,
        )
        assert created2 is False
        assert approval2.id == approval1.id

        # Só uma linha no banco.
        result = await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.pipeline_id == pipeline_id,
                ApprovalRequest.node_id == node_id,
                ApprovalRequest.checkpoint_id == interrupt_id,
            )
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1

    async def test_upsert_different_interrupt_id_creates_new(self, session: AsyncSession):
        """Chave diferente (interrupt_id) cria nova linha."""
        from app.approvals.service import upsert_approval_request

        user = await _create_user(session)
        owner_id = user.owner_id
        pipeline_id = uuid.uuid4()
        run_id = uuid.uuid4()
        node_id = "approval_node_e1"

        await upsert_approval_request(
            session,
            owner_id=owner_id,
            pipeline_id=pipeline_id,
            run_id=run_id,
            node_id=node_id,
            interrupt_id="task-id-1",
            payload={"message": "A"},
        )
        approval2, created2 = await upsert_approval_request(
            session,
            owner_id=owner_id,
            pipeline_id=pipeline_id,
            run_id=run_id,
            node_id=node_id,
            interrupt_id="task-id-2",
            payload={"message": "B"},
        )
        assert created2 is True
        assert approval2.message == "B"


# ---------------------------------------------------------------------------
# Teste 3: Respond nos três modos (API)
# ---------------------------------------------------------------------------


class TestRespondThreeModes:
    """Respond nos três modos: aprovar, rejeitar, argumentar."""

    async def test_respond_approve(self, session: AsyncSession):
        """Aprovar: status vira approved, emite approval:resolved."""
        user = await _create_user(session)
        pipeline = _make_pipeline(user.owner_id)
        session.add(pipeline)
        await session.commit()

        approval = _make_approval(user.owner_id, pipeline.id)
        session.add(approval)
        await session.commit()

        client = _make_client(session, user)
        with patch("app.api.approvals.ws_publish", new_callable=AsyncMock) as mock_pub:
            resp = await client.post(
                f"/api/approvals/{approval.id}/respond",
                json={"decision": "approved"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"

        # approval:resolved emitido.
        resolved_calls = [
            c for c in mock_pub.call_args_list if c[0][1] == "approval:resolved"
        ]
        assert len(resolved_calls) == 1
        assert resolved_calls[0][0][2]["decision"] == "approved"

    async def test_respond_reject(self, session: AsyncSession):
        """Rejeitar: status vira rejected."""
        user = await _create_user(session)
        pipeline = _make_pipeline(user.owner_id)
        session.add(pipeline)
        await session.commit()

        approval = _make_approval(user.owner_id, pipeline.id)
        session.add(approval)
        await session.commit()

        client = _make_client(session, user)
        with patch("app.api.approvals.ws_publish", new_callable=AsyncMock) as mock_pub:
            resp = await client.post(
                f"/api/approvals/{approval.id}/respond",
                json={"decision": "rejected"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        resolved_calls = [
            c for c in mock_pub.call_args_list if c[0][1] == "approval:resolved"
        ]
        assert resolved_calls[0][0][2]["decision"] == "rejected"

    async def test_respond_revise(self, session: AsyncSession):
        """Argumentar: status vira revised, response salvo."""
        user = await _create_user(session)
        pipeline = _make_pipeline(user.owner_id)
        session.add(pipeline)
        await session.commit()

        approval = _make_approval(user.owner_id, pipeline.id)
        session.add(approval)
        await session.commit()

        client = _make_client(session, user)
        with patch("app.api.approvals.ws_publish", new_callable=AsyncMock) as mock_pub:
            resp = await client.post(
                f"/api/approvals/{approval.id}/respond",
                json={"decision": "revised", "response": "Corrija o bug X"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "revised"

        # Response salvo.
        await session.refresh(approval)
        assert approval.response == "Corrija o bug X"

        resolved_calls = [
            c for c in mock_pub.call_args_list if c[0][1] == "approval:resolved"
        ]
        assert resolved_calls[0][0][2]["decision"] == "revised"


# ---------------------------------------------------------------------------
# Teste 4: Dupla resposta (409)
# ---------------------------------------------------------------------------


class TestDoubleRespond:
    """Responder duas vezes a mesma aprovação retorna 409."""

    async def test_double_respond_409(self, session: AsyncSession):
        """Segunda resposta retorna 409 already_responded."""
        user = await _create_user(session)
        pipeline = _make_pipeline(user.owner_id)
        session.add(pipeline)
        await session.commit()

        approval = _make_approval(user.owner_id, pipeline.id)
        session.add(approval)
        await session.commit()

        client = _make_client(session, user)
        with patch("app.api.approvals.ws_publish", new_callable=AsyncMock):
            # Primeira resposta: OK.
            resp1 = await client.post(
                f"/api/approvals/{approval.id}/respond",
                json={"decision": "approved"},
            )
            assert resp1.status_code == 200

            # Segunda resposta: 409.
            resp2 = await client.post(
                f"/api/approvals/{approval.id}/respond",
                json={"decision": "approved"},
            )
            assert resp2.status_code == 409
            assert resp2.json()["code"] == "already_responded"

    async def test_respond_cancelled_run_409(self, session: AsyncSession):
        """Responder uma aprovação de um run cancelado retorna 409."""
        from app.db.models import PipelineRun

        user = await _create_user(session)
        pipeline = _make_pipeline(user.owner_id)
        session.add(pipeline)
        await session.commit()

        from datetime import UTC, datetime

        run = PipelineRun(
            id=uuid.uuid4(),
            owner_id=user.owner_id,
            pipeline_id=pipeline.id,
            thread_id=f"{pipeline.id}:run1",
            status="cancelled",
            started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.commit()

        approval = _make_approval(user.owner_id, pipeline.id, run_id=run.id)
        session.add(approval)
        await session.commit()

        client = _make_client(session, user)
        with patch("app.api.approvals.ws_publish", new_callable=AsyncMock):
            resp = await client.post(
                f"/api/approvals/{approval.id}/respond",
                json={"decision": "approved"},
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "already_responded"


# ---------------------------------------------------------------------------
# Teste 5: Isolamento por owner
# ---------------------------------------------------------------------------


class TestOwnerIsolation:
    """Aprovações são filtradas por owner (V1 single-user)."""

    async def test_list_filtered_by_owner(self, session: AsyncSession):
        """Listar aprovações retorna só as do owner autenticado."""
        user_a = await _create_user(session, "a@test.com")
        user_b = await _create_user(session, "b@test.com")
        pipeline_a = _make_pipeline(user_a.owner_id)
        pipeline_b = _make_pipeline(user_b.owner_id)
        session.add(pipeline_a)
        session.add(pipeline_b)
        await session.commit()

        # Aprovação do owner A.
        approval_a = _make_approval(user_a.owner_id, pipeline_a.id)
        session.add(approval_a)
        # Aprovação do owner B.
        approval_b = _make_approval(user_b.owner_id, pipeline_b.id)
        session.add(approval_b)
        await session.commit()

        # Client autenticado como owner A.
        client = _make_client(session, user_a)
        resp = await client.get("/api/approvals")
        assert resp.status_code == 200
        data = resp.json()
        # Só a aprovação do owner A.
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(approval_a.id)

    async def test_get_other_owner_approval_404(self, session: AsyncSession):
        """Detalhar aprovação de outro owner retorna 404."""
        user_a = await _create_user(session, "a@test.com")
        user_b = await _create_user(session, "b@test.com")
        pipeline_b = _make_pipeline(user_b.owner_id)
        session.add(pipeline_b)
        await session.commit()

        # Aprovação do owner B.
        approval_b = _make_approval(user_b.owner_id, pipeline_b.id)
        session.add(approval_b)
        await session.commit()

        # Client autenticado como owner A.
        client = _make_client(session, user_a)
        resp = await client.get(f"/api/approvals/{approval_b.id}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "approval_not_found"


# ---------------------------------------------------------------------------
# Teste 6: Nó de aprovação roteia corretamente (integração com compiler)
# ---------------------------------------------------------------------------


class TestApprovalNodeRouting:
    """O nó de aprovação roteia via Command(goto=<id real>)."""

    async def test_approve_routes_to_target(
        self, worker: FakeWorker, saver: MemorySaver
    ):
        """Aprovar -> Command(goto=target) -> B executa."""
        pipeline = _approval_pipeline()
        graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)
        config = {"configurable": {"thread_id": "t3"}}
        state = initial_state()
        state["data"] = {"A": {"out": "hello"}}

        await graph.ainvoke(state, config=config)
        snap = graph.get_state(config)
        assert snap is not None
        assert any("approval_node" in n for n in snap.next)

        await graph.ainvoke(Command(resume="approved"), config=config)
        snap = graph.get_state(config)
        assert snap is not None
        assert snap.values["status"]["B"] == "completed"

    async def test_reject_loops_back(
        self, worker: FakeWorker, saver: MemorySaver
    ):
        """Rejeitar -> Command(goto=source) -> loop-back para A."""
        pipeline = _approval_pipeline()
        graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)
        config = {"configurable": {"thread_id": "t4"}}
        state = initial_state()
        state["data"] = {"A": {"out": "hello"}}

        await graph.ainvoke(state, config=config)
        snap = graph.get_state(config)
        assert snap is not None
        assert any("approval_node" in n for n in snap.next)

        await graph.ainvoke(Command(resume="rejected"), config=config)
        snap = graph.get_state(config)
        assert snap is not None
        # A executou de novo (loop-back).
        assert snap.values["iterations"]["A"] >= 2

    async def test_revise_injects_feedback(
        self, worker: FakeWorker, saver: MemorySaver
    ):
        """Argumentar -> feedback no State + Command(goto=target)."""
        pipeline = _approval_pipeline()
        graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)
        config = {"configurable": {"thread_id": "t5"}}
        state = initial_state()
        state["data"] = {"A": {"out": "hello"}}

        await graph.ainvoke(state, config=config)
        snap = graph.get_state(config)
        assert snap is not None
        assert any("approval_node" in n for n in snap.next)

        # Argumentar: feedback injetado no State (data[A].humanFeedback).
        await graph.ainvoke(
            Command(resume={"decision": "revised", "response": "Corrija X"}),
            config=config,
        )
        snap = graph.get_state(config)
        assert snap is not None
        # B executou (o nó roteou para B após o feedback).
        assert snap.values["status"]["B"] == "completed"
        # Feedback injetado no State (namespace do source A).
        assert snap.values["data"]["A"].get(HUMAN_FEEDBACK_KEY) == "Corrija X"


# ---------------------------------------------------------------------------
# Teste 7: Hook do executor (upsert + notificação)
# ---------------------------------------------------------------------------


class TestExecutorHook:
    """O hook do executor faz upsert + notificação (ADR-009)."""

    async def test_hook_upserts_and_notifies(
        self, session: AsyncSession, test_engine: Any
    ):
        """O hook cria a ApprovalRequest e emite approval:new."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.approvals.service import build_approval_hook

        user = await _create_user(session)
        pipeline = _make_pipeline(user.owner_id)
        session.add(pipeline)
        await session.commit()
        pipeline_id = pipeline.id

        # Session factory sobre a engine do teste (banco isolado).
        factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        hook = build_approval_hook(factory)

        run_id = str(uuid.uuid4())
        node_id = "approval_node_e1"
        payload = {
            "message": "Aprovar?",
            "context": {"out": "hello"},
            "__interruptId__": "task-id-1",
        }

        with patch("app.approvals.service.ws_publish", new_callable=AsyncMock) as mock_pub:
            await hook(run_id, str(pipeline_id), node_id, payload, "t1")

        # approval:new emitido.
        new_calls = [c for c in mock_pub.call_args_list if c[0][1] == "approval:new"]
        assert len(new_calls) == 1
        assert new_calls[0][0][2]["message"] == "Aprovar?"

        # ApprovalRequest criada.
        result = await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.pipeline_id == pipeline_id,
                ApprovalRequest.node_id == node_id,
            )
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert rows[0].status == "pending"

    async def test_hook_idempotent_no_renotify(
        self, session: AsyncSession, test_engine: Any
    ):
        """Segunda chamada do hook (mesma chave) não re-notifica."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.approvals.service import build_approval_hook

        user = await _create_user(session)
        pipeline = _make_pipeline(user.owner_id)
        session.add(pipeline)
        await session.commit()
        pipeline_id = pipeline.id

        factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        hook = build_approval_hook(factory)

        run_id = str(uuid.uuid4())
        node_id = "approval_node_e1"
        payload = {
            "message": "Aprovar?",
            "context": {},
            "__interruptId__": "task-id-1",
        }

        with patch("app.approvals.service.ws_publish", new_callable=AsyncMock) as mock_pub:
            # Primeira chamada: cria + notifica.
            await hook(run_id, str(pipeline_id), node_id, payload, "t1")
            # Segunda chamada (mesma chave): idempotente, não re-notifica.
            await hook(run_id, str(pipeline_id), node_id, payload, "t1")

        # Só UMA notificação (a primeira).
        new_calls = [c for c in mock_pub.call_args_list if c[0][1] == "approval:new"]
        assert len(new_calls) == 1
