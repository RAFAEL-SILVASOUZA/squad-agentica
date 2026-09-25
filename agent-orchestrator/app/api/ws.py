"""WebSocket endpoint router.

Dono: rt-websocket (FASE 6). Contrato §7:
- Conexão única: /api/ws?token=<JWT>.
- JWT validado no handshake via validate_ws_token (auth-backend).
- Token inválido: close com código policy violation (4000).
- Conexão associada a um owner (ownerId = sub claim).
- O servidor envia eventos de todas as pipelines do owner;
  o cliente filtra pelo pipelineId do payload.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.dependencies import validate_ws_token
from app.core.errors import AppError
from app.runtime.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint: /api/ws?token=<JWT>.

    Handshake:
    1. Extract token from query string.
    2. Validate via validate_ws_token (raises AppError on failure).
    3. Accept connection, register with ConnectionManager.
    4. Loop: receive (discard client messages), handle disconnect.

    The server is push-only: it sends frames to the client but does not
    process client messages (no subscribe protocol per contract §7).
    """
    token = websocket.query_params.get("token")
    if not token:
        # No token: reject with policy violation.
        await websocket.close(code=4000, reason="missing token")
        return

    try:
        payload = validate_ws_token(token)
    except AppError:
        # Invalid/expired/wrong-type token: policy violation.
        await websocket.close(code=4000, reason="invalid token")
        return

    owner_id: str = payload["sub"]

    try:
        await manager.connect(websocket, owner_id)
    except Exception:
        logger.exception("ws_connect_failed", extra={"owner_id": owner_id})
        await websocket.close(code=1011, reason="internal error")
        return

    try:
        # Server-push only: we keep the connection open and discard any
        # client messages. The loop exits when the client disconnects.
        while True:
            # Receive will raise WebSocketDisconnect when the client closes.
            # We don't process the message content (no subscribe protocol).
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_loop_error", extra={"owner_id": owner_id})
    finally:
        await manager.disconnect(websocket, owner_id)
