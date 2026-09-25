"""Notification channel interface and type declarations.

Dono: hitl-notification (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md §11.7 (C-01: NotificationChannel declarado).
- PLANO-BACKEND.md §2.21 (contrato que expõe).
- Spec 4.5 (ApprovalRequest.channel, attemptedChannels, fallbackChannel).

NotificationChannel é um Literal (não um Enum Python) para alinhar com o
Enum do SQLAlchemy no model (native_enum=False, string values).
"""

from __future__ import annotations

from typing import Literal, Protocol

from app.db.models import ApprovalRequest

# NotificationChannel: os 4 canais declarados (C-01 do contrato §11.7).
# V1: in-app (WebSocket) + email (SMTP, desligado por padrão).
# V2: teams, slack.
NotificationChannel = Literal["in-app", "email", "teams", "slack"]


class ChannelNotifier(Protocol):
    """Protocolo que todo canal de notificação implementa.

    Cada canal implementa ``send`` que recebe a ApprovalRequest e envia a
    notificação pelo canal específico. Se o canal falhar, levanta
    ``NotificationError`` (o service trata retry/fallback).
    """

    name: NotificationChannel

    async def send(self, approval: ApprovalRequest, response_url: str | None = None) -> None:
        """Envia a notificação pelo canal.

        Args:
            approval: A ApprovalRequest persistida.
            response_url: URL opcional para o humano responder (email).

        Raises:
            NotificationError: se o envio falhar.
        """
        ...
