"""Notification delivery service: retry, timeout, fallback.

Dono: hitl-notification (FASE 7). Fontes de verdade:
- PLANO-BACKEND.md §2.21 (notify_with_fallback: tenta primary; se falhar,
  tenta fallback_channel até max_retries. Nunca propaga exceção).
- D7 §7.7 (retry + fallback: retryCount/attemptedChannels no ApprovalRequest).
- Spec 14 (risco: "Notificação não chega" → Retry + timeout + fallback).
- CONTRATO-TECNICO.md §10 (in-app V1, email opcional, teams/slack V2).

Fluxo:
1. Tenta o canal primário (``primary``).
2. Se falhar, incrementa ``retry_count`` e adiciona ao ``attempted_channels``.
3. Se ``retry_count < max_retries``, tenta de novo (mesmo canal).
4. Se esgotou retries no primário, tenta o ``fallback_channel`` (se definido).
5. Se todos falharem, loga e retorna (nunca propaga exceção para o nó).

O service atualiza a ApprovalRequest no banco com os campos de retry.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalRequest
from app.notifications.email import EmailChannel
from app.notifications.inapp import InAppChannel, NotificationError
from app.notifications.interface import ChannelNotifier, NotificationChannel
from app.notifications.slack import SlackChannel
from app.notifications.teams import TeamsChannel

logger = logging.getLogger(__name__)

# Timeout por tentativa de envio (segundos).
SEND_TIMEOUT = 30.0


def get_channel(name: NotificationChannel) -> ChannelNotifier:
    """Factory: retorna a instância do canal pelo nome.

    Args:
        name: Nome do canal ("in-app", "email", "teams", "slack").

    Returns:
        Instância do canal.

    Raises:
        ValueError: se o canal não é reconhecido.
    """
    channels: dict[str, ChannelNotifier] = {
        "in-app": InAppChannel(),
        "email": EmailChannel(),
        "teams": TeamsChannel(),
        "slack": SlackChannel(),
    }
    channel = channels.get(name)
    if channel is None:
        raise ValueError(f"Unknown notification channel: {name}")
    return channel


async def notify(
    session: AsyncSession,
    approval: ApprovalRequest,
    channel: NotificationChannel,
    response_url: str | None = None,
) -> bool:
    """Dispara a notificação pelo canal especificado.

    Atualiza a ApprovalRequest com ``attempted_channels`` e ``retry_count``.

    Args:
        session: Sessão SQLAlchemy async (para atualizar a ApprovalRequest).
        approval: A ApprovalRequest persistida.
        channel: Canal a usar.
        response_url: URL opcional para o humano responder.

    Returns:
        True se a notificação foi entregue com sucesso, False se falhou.
    """
    notifier = get_channel(channel)
    try:
        await notifier.send(approval, response_url=response_url)
        # Sucesso: registra o canal tentado.
        if channel not in approval.attempted_channels:
            approval.attempted_channels = [*approval.attempted_channels, channel]
        await session.commit()
        return True
    except NotificationError:
        # Falha: registra tentativa.
        approval.retry_count += 1
        if channel not in approval.attempted_channels:
            approval.attempted_channels = [*approval.attempted_channels, channel]
        await session.commit()
        logger.warning(
            "notification channel failed",
            extra={
                "approval_id": str(approval.id),
                "channel": channel,
                "retry_count": approval.retry_count,
            },
        )
        return False
    except Exception as exc:
        # Erro inesperado: registra e retorna False.
        approval.retry_count += 1
        if channel not in approval.attempted_channels:
            approval.attempted_channels = [*approval.attempted_channels, channel]
        await session.commit()
        logger.error(
            "notification channel unexpected error",
            extra={
                "approval_id": str(approval.id),
                "channel": channel,
                "error": str(exc),
            },
        )
        return False


async def notify_with_fallback(
    session: AsyncSession,
    approval: ApprovalRequest,
    primary: NotificationChannel,
    response_url: str | None = None,
) -> bool:
    """Envia notificação com retry e fallback de canal.

    Estratégia (D7 §7.7, PLANO-BACKEND §2.21):
    1. Tenta o canal ``primary`` até ``max_retries`` vezes.
    2. Se esgotar retries no primário, tenta o ``fallback_channel`` (se definido).
    3. Nunca propaga exceção (o canal falho não trava a pipeline).

    Args:
        session: Sessão SQLAlchemy async.
        approval: A ApprovalRequest persistida.
        primary: Canal primário.
        response_url: URL opcional para o humano responder.

    Returns:
        True se a notificação foi entregue por qualquer canal, False se todos falharam.
    """
    # Tenta o canal primário com retry.
    for attempt in range(approval.max_retries):
        success = await notify(session, approval, primary, response_url=response_url)
        if success:
            logger.info(
                "notification delivered (primary)",
                extra={
                    "approval_id": str(approval.id),
                    "channel": primary,
                    "attempt": attempt + 1,
                },
            )
            return True

    # Primário esgotou retries. Tenta fallback.
    fallback = approval.fallback_channel
    if fallback is not None and fallback != primary:
        logger.info(
            "trying fallback channel",
            extra={
                "approval_id": str(approval.id),
                "primary": primary,
                "fallback": str(fallback),
            },
        )
        success = await notify(session, approval, str(fallback), response_url=response_url)
        if success:
            logger.info(
                "notification delivered (fallback)",
                extra={
                    "approval_id": str(approval.id),
                    "channel": str(fallback),
                },
            )
            return True

    # Todos os canais falharam. Loga e retorna False (nunca propaga).
    logger.error(
        "all notification channels failed",
        extra={
            "approval_id": str(approval.id),
            "primary": primary,
            "fallback": str(fallback) if fallback else None,
            "retry_count": approval.retry_count,
            "attempted_channels": approval.attempted_channels,
        },
    )
    return False
