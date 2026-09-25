"""Testes do service de notificação: retry, fallback, timeout.

Dono: hitl-notification (FASE 7).
Critérios de aceite (PLANO-BACKEND §2.21):
(c) canal principal simulado como falho → fallback é tentado.
(d) todos os canais falham → exceção não escapa para o nó (log + continue).

Testes adicionais (prompt):
- Falha do canal primário aciona retry e depois fallback.
- Timeout registrado.
- Isolamento por owner.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalRequest
from app.notifications.inapp import InAppChannel, NotificationError
from app.notifications.service import get_channel, notify, notify_with_fallback


@pytest.fixture
def approval() -> ApprovalRequest:
    """Cria uma ApprovalRequest em memória (sem banco)."""
    return ApprovalRequest(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        pipeline_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="approval_node_e1",
        checkpoint_id="task-789",
        message="Aprovar?",
        context={},
        status="pending",
        channel="in-app",
        sent_at=datetime.now(UTC),
        retry_count=0,
        max_retries=3,
        attempted_channels=[],
        fallback_channel="email",
        timeout_seconds=3600,
    )


class TestNotifyWithFallback:
    """Testes do notify_with_fallback (retry + fallback)."""

    @pytest.mark.asyncio
    async def test_primary_success_no_fallback(self, approval: ApprovalRequest) -> None:
        """Se o primário funciona, não tenta fallback."""
        mock_session = AsyncMock(spec=AsyncSession)
        _inapp_patch = "app.notifications.service.InAppChannel.send"

        with patch(_inapp_patch, new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            result = await notify_with_fallback(
                mock_session, approval, "in-app"
            )

            assert result is True
            # InApp chamado 1x (sucesso na primeira tentativa).
            assert mock_send.call_count == 1
            # Email não chamado.
            assert "email" not in approval.attempted_channels

    @pytest.mark.asyncio
    async def test_primary_failure_triggers_retry(self, approval: ApprovalRequest) -> None:
        """Se o primário falha, tenta de novo até max_retries."""
        mock_session = AsyncMock(spec=AsyncSession)
        approval.max_retries = 3
        _inapp_patch = "app.notifications.service.InAppChannel.send"

        with patch(_inapp_patch, new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = NotificationError("in-app", "WS down")
            await notify_with_fallback(mock_session, approval, "in-app")

            # Falhou 3x (max_retries=3).
            assert mock_send.call_count == 3
            assert approval.retry_count == 3
            assert "in-app" in approval.attempted_channels

    @pytest.mark.asyncio
    async def test_primary_failure_triggers_fallback(self, approval: ApprovalRequest) -> None:
        """Se o primário esgota retries, tenta o fallback."""
        mock_session = AsyncMock(spec=AsyncSession)
        approval.max_retries = 2
        approval.fallback_channel = "email"
        _inapp = "app.notifications.service.InAppChannel.send"
        _email = "app.notifications.service.EmailChannel.send"

        with (
            patch(_inapp, new_callable=AsyncMock) as mock_inapp,
            patch(_email, new_callable=AsyncMock) as mock_email,
        ):
            mock_inapp.side_effect = NotificationError("in-app", "WS down")
            mock_email.return_value = None

            result = await notify_with_fallback(
                mock_session, approval, "in-app"
            )

            # InApp falhou 2x (max_retries=2).
            assert mock_inapp.call_count == 2
            # Email (fallback) foi tentado 1x e funcionou.
            assert mock_email.call_count == 1
            assert result is True
            assert "email" in approval.attempted_channels

    @pytest.mark.asyncio
    async def test_all_channels_fail_no_exception(self, approval: ApprovalRequest) -> None:
        """Se todos os canais falham, não propaga exceção (log + continue)."""
        mock_session = AsyncMock(spec=AsyncSession)
        approval.max_retries = 2
        approval.fallback_channel = "email"
        _inapp = "app.notifications.service.InAppChannel.send"
        _email = "app.notifications.service.EmailChannel.send"

        with (
            patch(_inapp, new_callable=AsyncMock) as mock_inapp,
            patch(_email, new_callable=AsyncMock) as mock_email,
        ):
            mock_inapp.side_effect = NotificationError("in-app", "WS down")
            mock_email.side_effect = NotificationError("email", "SMTP down")

            # Não deve levantar exceção.
            result = await notify_with_fallback(
                mock_session, approval, "in-app"
            )

            assert result is False
            # Ambos os canais foram tentados.
            assert "in-app" in approval.attempted_channels
            assert "email" in approval.attempted_channels

    @pytest.mark.asyncio
    async def test_no_fallback_defined(self, approval: ApprovalRequest) -> None:
        """Se não há fallback definido, só tenta o primário."""
        mock_session = AsyncMock(spec=AsyncSession)
        approval.max_retries = 2
        approval.fallback_channel = None
        _inapp = "app.notifications.service.InAppChannel.send"

        with patch(_inapp, new_callable=AsyncMock) as mock_inapp:
            mock_inapp.side_effect = NotificationError("in-app", "WS down")

            result = await notify_with_fallback(
                mock_session, approval, "in-app"
            )

            assert result is False
            assert mock_inapp.call_count == 2
            # Email não tentado (fallback=None).
            assert "email" not in approval.attempted_channels

    @pytest.mark.asyncio
    async def test_timeout_registered(self, approval: ApprovalRequest) -> None:
        """Timeout do canal é registrado (retry_count incrementa)."""
        mock_session = AsyncMock(spec=AsyncSession)
        approval.max_retries = 1
        approval.fallback_channel = None  # Sem fallback: só o primário.
        _inapp = "app.notifications.service.InAppChannel.send"

        with patch(_inapp, new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = NotificationError("in-app", "timeout after 30s")

            result = await notify_with_fallback(
                mock_session, approval, "in-app"
            )

            assert result is False
            assert approval.retry_count == 1
            assert "in-app" in approval.attempted_channels


class TestNotifySingle:
    """Testes do notify (single channel, sem fallback)."""

    @pytest.mark.asyncio
    async def test_notify_success(self, approval: ApprovalRequest) -> None:
        """notify retorna True quando o canal funciona."""
        mock_session = AsyncMock(spec=AsyncSession)
        _inapp = "app.notifications.service.InAppChannel.send"

        with patch(_inapp, new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            result = await notify(mock_session, approval, "in-app")

            assert result is True
            assert "in-app" in approval.attempted_channels
            assert approval.retry_count == 0

    @pytest.mark.asyncio
    async def test_notify_failure_increments_retry(self, approval: ApprovalRequest) -> None:
        """notify retorna False e incrementa retry_count quando falha."""
        mock_session = AsyncMock(spec=AsyncSession)
        _inapp = "app.notifications.service.InAppChannel.send"

        with patch(_inapp, new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = NotificationError("in-app", "fail")
            result = await notify(mock_session, approval, "in-app")

            assert result is False
            assert approval.retry_count == 1
            assert "in-app" in approval.attempted_channels


class TestGetChannel:
    """Testes da factory get_channel."""

    def test_get_inapp(self) -> None:
        """get_channel('in-app') retorna InAppChannel."""
        channel = get_channel("in-app")
        assert isinstance(channel, InAppChannel)

    def test_get_unknown_raises(self) -> None:
        """get_channel com nome inválido levanta ValueError."""
        with pytest.raises(ValueError, match="Unknown notification channel"):
            get_channel("carrier-pigeon")  # type: ignore[arg-type]


class TestOwnerIsolation:
    """Isolamento por owner: o evento vai para o owner correto."""

    @pytest.mark.asyncio
    async def test_inapp_publishes_to_correct_owner(self, approval: ApprovalRequest) -> None:
        """O in-app publica para o owner_id da ApprovalRequest."""
        channel = InAppChannel()
        expected_owner = str(approval.owner_id)

        with patch("app.notifications.inapp.ws_publish", new_callable=AsyncMock) as mock_publish:
            await channel.send(approval)

            assert mock_publish.call_args[0][0] == expected_owner

    @pytest.mark.asyncio
    async def test_different_owners_different_events(self) -> None:
        """Dois owners diferentes recebem eventos separados."""
        owner1 = uuid.uuid4()
        owner2 = uuid.uuid4()

        approval1 = ApprovalRequest(
            id=uuid.uuid4(),
            owner_id=owner1,
            pipeline_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            node_id="n1",
            checkpoint_id="cp1",
            message="msg1",
            context={},
            status="pending",
            channel="in-app",
            sent_at=datetime.now(UTC),
            retry_count=0,
            max_retries=3,
            attempted_channels=[],
            fallback_channel=None,
            timeout_seconds=3600,
        )
        approval2 = ApprovalRequest(
            id=uuid.uuid4(),
            owner_id=owner2,
            pipeline_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            node_id="n2",
            checkpoint_id="cp2",
            message="msg2",
            context={},
            status="pending",
            channel="in-app",
            sent_at=datetime.now(UTC),
            retry_count=0,
            max_retries=3,
            attempted_channels=[],
            fallback_channel=None,
            timeout_seconds=3600,
        )

        channel = InAppChannel()

        with patch("app.notifications.inapp.ws_publish", new_callable=AsyncMock) as mock_publish:
            await channel.send(approval1)
            await channel.send(approval2)

            assert mock_publish.call_count == 2
            # Primeiro evento para owner1.
            assert mock_publish.call_args_list[0][0][0] == str(owner1)
            # Segundo evento para owner2.
            assert mock_publish.call_args_list[1][0][0] == str(owner2)
