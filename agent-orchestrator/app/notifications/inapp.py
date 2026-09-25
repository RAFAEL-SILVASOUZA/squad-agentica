"""In-app notification channel (WebSocket).

Dono: hitl-notification (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md §7 (canais WebSocket, publish interface).
- PLANO-BACKEND.md §2.21 (in-app = publish(owner_id, "approval:new", payload)).
- D7 §7.5 (após persistir, emitir approval:new via WebSocket).
- Spec 9.7 (canal approval:new).

O canal in-app publica o evento ``approval:new`` via a interface ``publish``
do rt-websocket. O payload segue o contrato §7:
    { "approvalId": str, "pipelineId": str, "runId": str,
      "nodeId": str, "message": str, "at": iso8601 }
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db.models import ApprovalRequest
from app.notifications.interface import NotificationChannel
from app.runtime.websocket import publish as ws_publish

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Erro no envio de notificação (canal falhou)."""

    def __init__(self, channel: str, message: str) -> None:
        super().__init__(f"[{channel}] {message}")
        self.channel = channel
        self.message = message


def _now_iso() -> str:
    """Timestamp ISO 8601 UTC com Z explícito (contrato §8)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class InAppChannel:
    """Canal in-app: publica ``approval:new`` via WebSocket.

    V1: é o canal primário. O portal recebe o evento em tempo real
    (badge + tela de aprovação).
    """

    name: NotificationChannel = "in-app"

    async def send(self, approval: ApprovalRequest, response_url: str | None = None) -> None:
        """Publica o evento approval:new para o owner via WebSocket.

        Args:
            approval: A ApprovalRequest persistida.
            response_url: Não usado no canal in-app (o portal já tem a rota).

        Raises:
            NotificationError: se a publicação falhar.
        """
        try:
            await ws_publish(
                str(approval.owner_id),
                "approval:new",
                {
                    "approvalId": str(approval.id),
                    "pipelineId": str(approval.pipeline_id),
                    "runId": str(approval.run_id) if approval.run_id else None,
                    "nodeId": approval.node_id,
                    "message": approval.message,
                    "at": _now_iso(),
                },
            )
            logger.info(
                "in-app notification sent",
                extra={
                    "approval_id": str(approval.id),
                    "owner_id": str(approval.owner_id),
                },
            )
        except Exception as exc:
            logger.error(
                "in-app notification failed",
                extra={
                    "approval_id": str(approval.id),
                    "error": str(exc),
                },
            )
            raise NotificationError("in-app", str(exc)) from exc
