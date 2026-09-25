"""Slack notification channel (STUB para V2).

Dono: hitl-notification (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md §10 (Teams/Slack são stubs para V2).
- PLANO-BACKEND.md §2.21 (teams/slack = stubs que logam "not implemented").

Na V1, este canal é um stub: loga "not implemented" e retorna sem erro.
O service de notificação trata como "sucesso" (não tenta fallback).
"""

from __future__ import annotations

import logging

from app.db.models import ApprovalRequest
from app.notifications.interface import NotificationChannel

logger = logging.getLogger(__name__)


class SlackChannel:
    """Canal Slack (stub V2).

    Na V1: loga "not implemented" e retorna. Não levanta exceção.
    """

    name: NotificationChannel = "slack"

    async def send(self, approval: ApprovalRequest, response_url: str | None = None) -> None:
        """Stub: loga e retorna (V2)."""
        logger.info(
            "slack notification not implemented (V2)",
            extra={"approval_id": str(approval.id)},
        )
