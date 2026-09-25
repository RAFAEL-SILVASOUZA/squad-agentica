"""WebSocket ConnectionManager and publish interface.

Dono: rt-websocket (FASE 6). Contrato §7:
- Conexão única em /api/ws?token=<JWT>.
- Frames: {"channel": <string>, "data": <any>}.
- Canais: pipeline:status, pipeline:log, approval:new, approval:resolved, agent:output.
- Filtro por ownerId; cliente não manda subscribe.
- publish(owner_id, channel, data) é a interface que executor/HITL consomem.
- Heartbeat (ping) para NGINX não derrubar conexões ociosas.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)

# Valid channels (spec 9.7, contrato §7).
VALID_CHANNELS: frozenset[str] = frozenset(
    {
        "pipeline:status",
        "pipeline:log",
        "approval:new",
        "approval:resolved",
        "agent:output",
    }
)

# Heartbeat interval in seconds (NGINX proxy_read_timeout is 3600s;
# we ping every 30s to keep the connection alive through any intermediate
# proxy or load balancer that might have shorter idle timeouts).
HEARTBEAT_INTERVAL: float = 30.0


class ConnectionManager:
    """Manages WebSocket connections grouped by owner.

    Thread-safe via asyncio (single event loop). Supports multiple
    connections per owner. Dead connections are removed gracefully
    without breaking the broadcast to other connections.

    Usage:
        manager = ConnectionManager()
        await manager.connect(websocket, owner_id)
        await manager.publish(owner_id, "pipeline:status", {...})
        await manager.disconnect(websocket, owner_id)
    """

    def __init__(self) -> None:
        # owner_id -> set of (websocket, heartbeat_task)
        self._connections: dict[str, set[tuple[WebSocket, asyncio.Task | None]]] = {}
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """Total number of active connections across all owners."""
        return sum(len(conns) for conns in self._connections.values())

    async def connect(self, websocket: WebSocket, owner_id: str) -> None:
        """Accept a WebSocket connection and register it for the owner.

        Starts a heartbeat task for the connection.
        """
        await websocket.accept()
        heartbeat_task = asyncio.create_task(
            self._heartbeat(websocket), name=f"ws-heartbeat-{owner_id}"
        )
        async with self._lock:
            self._connections.setdefault(owner_id, set()).add((websocket, heartbeat_task))
        logger.info(
            "ws_connected",
            extra={"owner_id": owner_id, "total": self.connection_count},
        )

    async def disconnect(self, websocket: WebSocket, owner_id: str) -> None:
        """Remove a WebSocket connection for the owner.

        Cancels the heartbeat task. Safe to call multiple times.
        """
        async with self._lock:
            conns = self._connections.get(owner_id)
            if conns is None:
                return
            to_remove = None
            for ws, task in conns:
                if ws is websocket:
                    to_remove = (ws, task)
                    break
            if to_remove is not None:
                conns.discard(to_remove)
                if task is not None:
                    task.cancel()
            if not conns:
                del self._connections[owner_id]
        logger.info(
            "ws_disconnected",
            extra={"owner_id": owner_id, "total": self.connection_count},
        )

    async def publish(self, owner_id: str, channel: str, data: Any) -> None:
        """Publish a frame to all connections of the given owner.

        Dead connections are silently removed. If no connections exist
        for the owner, the message is dropped (no error).

        Args:
            owner_id: The owner to publish to.
            channel: One of the valid channels.
            data: The payload (will be JSON-serialized).
        """
        if channel not in VALID_CHANNELS:
            logger.warning("ws_invalid_channel", extra={"channel": channel})
            return

        frame = json.dumps({"channel": channel, "data": data}, default=str)

        async with self._lock:
            conns = self._connections.get(owner_id)
            if not conns:
                return
            # Copy to avoid mutation during iteration.
            targets = list(conns)

        dead: list[tuple[WebSocket, asyncio.Task | None]] = []
        for ws, _task in targets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(frame)
                else:
                    # Already disconnected: mark for cleanup.
                    dead.append((ws, _task))
            except Exception:
                dead.append((ws, _task))

        # Remove dead connections.
        if dead:
            async with self._lock:
                conns = self._connections.get(owner_id)
                if conns is not None:
                    for ws, task in dead:
                        conns.discard((ws, task))
                        if task is not None:
                            task.cancel()
                    if not conns:
                        del self._connections[owner_id]
            logger.info(
                "ws_dead_connections_removed",
                extra={"owner_id": owner_id, "count": len(dead)},
            )

    async def _heartbeat(self, websocket: WebSocket) -> None:
        """Send periodic pings to keep the connection alive.

        Runs until cancelled or the connection is closed.
        """
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(json.dumps({"channel": "heartbeat", "data": None}))
        except asyncio.CancelledError:
            pass
        except Exception:
            # Connection is dead; the publish loop will clean it up.
            pass

    async def shutdown(self) -> None:
        """Close all connections (graceful shutdown)."""
        async with self._lock:
            for _owner_id, conns in list(self._connections.items()):
                for ws, task in conns:
                    if task is not None:
                        task.cancel()
                    try:
                        if ws.client_state == WebSocketState.CONNECTED:
                            await ws.close(code=1001)
                    except Exception:
                        pass
            self._connections.clear()


# Module-level singleton (importable without side effects).
manager = ConnectionManager()


async def publish(owner_id: str, channel: str, data: Any) -> None:
    """Publish an event to all WebSocket connections of the given owner.

    This is the public interface consumed by rt-executor and hitl-approval.
    Importable without side effects:
        from app.runtime.websocket import publish
        await publish(owner_id, "pipeline:status", {...})
    """
    await manager.publish(owner_id, channel, data)
