"""Tests for WebSocket ConnectionManager and /api/ws endpoint.

Dono: rt-websocket (FASE 6). Contrato §7:
- Conexão com token válido e inválido.
- Isolamento entre owners.
- Publicação para múltiplas conexões.
- Conexão morta não quebra o envio.
- Formato dos frames.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.auth.jwt import create_access_token, create_refresh_token
from app.runtime.websocket import VALID_CHANNELS, ConnectionManager, publish  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def owner_b() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def valid_token_a(owner_a: str) -> str:
    return create_access_token(owner_a)


@pytest.fixture
def valid_token_b(owner_b: str) -> str:
    return create_access_token(owner_b)


@pytest.fixture
def manager() -> ConnectionManager:
    """Fresh ConnectionManager per test (no shared state)."""
    return ConnectionManager()


@pytest.fixture
def ws_app(manager: ConnectionManager) -> FastAPI:
    """Minimal FastAPI app with the WS endpoint, using the test manager."""
    app = FastAPI()

    @app.websocket("/api/ws")
    async def _ws(websocket: WebSocket) -> None:
        # Reuse the endpoint logic but with our test manager.
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4000, reason="missing token")
            return

        from app.auth.dependencies import validate_ws_token
        from app.core.errors import AppError

        try:
            payload = validate_ws_token(token)
        except AppError:
            await websocket.close(code=4000, reason="invalid token")
            return

        owner_id: str = payload["sub"]
        await manager.connect(websocket, owner_id)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(websocket, owner_id)

    return app


@pytest.fixture
def client(ws_app: FastAPI) -> TestClient:
    return TestClient(ws_app)


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """Unit tests for ConnectionManager (no HTTP layer)."""

    async def test_connect_and_disconnect(self, manager: ConnectionManager) -> None:
        """Connection is registered and unregistered."""
        ws = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws, owner)
        assert manager.connection_count == 1

        await manager.disconnect(ws, owner)
        assert manager.connection_count == 0

    async def test_multiple_connections_same_owner(self, manager: ConnectionManager) -> None:
        """Multiple connections for the same owner are all tracked."""
        ws1 = _FakeWebSocket()
        ws2 = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws1, owner)
        await manager.connect(ws2, owner)
        assert manager.connection_count == 2

        await manager.disconnect(ws1, owner)
        assert manager.connection_count == 1

        await manager.disconnect(ws2, owner)
        assert manager.connection_count == 0

    async def test_publish_sends_to_all_connections(self, manager: ConnectionManager) -> None:
        """publish() sends the frame to all connections of the owner."""
        ws1 = _FakeWebSocket()
        ws2 = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws1, owner)
        await manager.connect(ws2, owner)

        data = {
            "pipelineId": "p1", "runId": "r1", "nodeId": "n1",
            "status": "running", "at": "2026-01-01T00:00:00Z",
        }
        await manager.publish(owner, "pipeline:status", data)

        expected_frame = json.dumps({"channel": "pipeline:status", "data": data}, default=str)
        assert ws1.sent_messages == [expected_frame]
        assert ws2.sent_messages == [expected_frame]

    async def test_publish_isolation_between_owners(self, manager: ConnectionManager) -> None:
        """publish() only reaches connections of the target owner."""
        ws_a = _FakeWebSocket()
        ws_b = _FakeWebSocket()
        owner_a = str(uuid.uuid4())
        owner_b = str(uuid.uuid4())

        await manager.connect(ws_a, owner_a)
        await manager.connect(ws_b, owner_b)

        data = {
            "pipelineId": "p1", "runId": "r1", "nodeId": "n1",
            "status": "running", "at": "2026-01-01T00:00:00Z",
        }
        await manager.publish(owner_a, "pipeline:status", data)

        assert len(ws_a.sent_messages) == 1
        assert ws_b.sent_messages == []  # owner_b gets nothing

    async def test_publish_invalid_channel_ignored(self, manager: ConnectionManager) -> None:
        """publish() with an invalid channel is silently dropped."""
        ws = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws, owner)
        await manager.publish(owner, "invalid:channel", {"foo": "bar"})

        assert ws.sent_messages == []

    async def test_publish_no_connections_no_error(self, manager: ConnectionManager) -> None:
        """publish() to an owner with no connections is a no-op."""
        owner = str(uuid.uuid4())
        # Should not raise.
        await manager.publish(owner, "pipeline:status", {"foo": "bar"})

    async def test_dead_connection_removed_on_publish(self, manager: ConnectionManager) -> None:
        """A dead connection is removed without breaking the broadcast."""
        ws_dead = _FakeWebSocket()
        ws_alive = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws_dead, owner)
        await manager.connect(ws_alive, owner)

        # Make ws_dead fail on send.
        ws_dead.client_state = WebSocketState.DISCONNECTED

        data = {
            "pipelineId": "p1", "runId": "r1", "nodeId": "n1",
            "status": "running", "at": "2026-01-01T00:00:00Z",
        }
        await manager.publish(owner, "pipeline:status", data)

        # Alive connection still got the message.
        assert len(ws_alive.sent_messages) == 1
        # Dead connection was removed.
        assert manager.connection_count == 1

    async def test_dead_connection_exception_on_send(self, manager: ConnectionManager) -> None:
        """A connection that raises on send is removed gracefully."""
        ws_dead = _FakeWebSocket()
        ws_alive = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws_dead, owner)
        await manager.connect(ws_alive, owner)

        # Make ws_dead raise on send_text.
        ws_dead.send_text = AsyncMock(
            side_effect=RuntimeError("connection lost")
        )  # type: ignore[assignment]

        data = {
            "pipelineId": "p1", "runId": "r1", "nodeId": "n1",
            "status": "running", "at": "2026-01-01T00:00:00Z",
        }
        await manager.publish(owner, "pipeline:status", data)

        # Alive connection still got the message.
        assert len(ws_alive.sent_messages) == 1
        # Dead connection was removed.
        assert manager.connection_count == 1

    async def test_frame_format(self, manager: ConnectionManager) -> None:
        """Frames follow the {"channel": str, "data": any} format."""
        ws = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws, owner)
        data = {
            "approvalId": "a1", "pipelineId": "p1", "runId": "r1",
            "nodeId": "n1", "message": "approve?", "at": "2026-01-01T00:00:00Z",
        }
        await manager.publish(owner, "approval:new", data)

        frame = json.loads(ws.sent_messages[0])
        assert set(frame.keys()) == {"channel", "data"}
        assert frame["channel"] == "approval:new"
        assert frame["data"] == data

    async def test_all_valid_channels(self, manager: ConnectionManager) -> None:
        """All 5 contract channels are accepted."""
        ws = _FakeWebSocket()
        owner = str(uuid.uuid4())

        await manager.connect(ws, owner)
        for channel in VALID_CHANNELS:
            await manager.publish(owner, channel, {"test": True})

        assert len(ws.sent_messages) == len(VALID_CHANNELS)
        received_channels = {json.loads(m)["channel"] for m in ws.sent_messages}
        assert received_channels == VALID_CHANNELS


# ---------------------------------------------------------------------------
# publish() module-level function tests
# ---------------------------------------------------------------------------


class TestPublishFunction:
    """Tests for the module-level publish() function."""

    async def test_publish_uses_global_manager(self) -> None:
        """publish() delegates to the module-level manager."""
        from app.runtime import websocket as ws_module

        original_manager = ws_module.manager
        test_manager = ConnectionManager()
        ws_module.manager = test_manager

        try:
            ws = _FakeWebSocket()
            owner = str(uuid.uuid4())
            await test_manager.connect(ws, owner)

            await publish(owner, "pipeline:log", {"level": "info", "message": "hello"})

            frame = json.loads(ws.sent_messages[0])
            assert frame["channel"] == "pipeline:log"
            assert frame["data"]["message"] == "hello"
        finally:
            ws_module.manager = original_manager


# ---------------------------------------------------------------------------
# Integration tests: /api/ws endpoint via TestClient
# ---------------------------------------------------------------------------


class TestWebSocketEndpoint:
    """Integration tests for the /api/ws WebSocket endpoint."""

    def test_valid_token_connects(self, client: TestClient, valid_token_a: str) -> None:
        """Connection with a valid token is accepted."""
        with client.websocket_connect(f"/api/ws?token={valid_token_a}"):
            # Connection is open (no exception means accepted).
            pass

    def test_invalid_token_rejected(self, client: TestClient) -> None:
        """Connection with an invalid token is closed with policy violation."""
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws?token=invalid.token.here"):
                pass

    def test_missing_token_rejected(self, client: TestClient) -> None:
        """Connection without a token is closed with policy violation."""
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws"):
                pass

    def test_refresh_token_rejected(self, client: TestClient, owner_a: str) -> None:
        """Connection with a refresh token (wrong type) is rejected."""
        token = create_refresh_token(owner_a)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/ws?token={token}"):
                pass


# ---------------------------------------------------------------------------
# Fake WebSocket for unit tests
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Minimal fake WebSocket for ConnectionManager unit tests."""

    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.sent_messages: list[str] = []

    async def accept(self) -> None:
        pass

    async def send_text(self, data: str) -> None:
        if self.client_state != WebSocketState.CONNECTED:
            raise RuntimeError("not connected")
        self.sent_messages.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_text(self) -> str:
        raise WebSocketDisconnect(code=1000)
