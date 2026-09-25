"""Testes do canal email (desligado por padrão).

Dono: hitl-notification (FASE 7).
Critérios de aceite (PLANO-BACKEND §2.21):
(b) email não é enviado quando ENABLE_EMAIL_NOTIFICATIONS=false.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.db.models import ApprovalRequest
from app.notifications.email import EmailChannel
from app.notifications.inapp import NotificationError


@pytest.fixture
def approval() -> ApprovalRequest:
    """Cria uma ApprovalRequest em memória (sem banco)."""
    return ApprovalRequest(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        pipeline_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="approval_node_e1",
        checkpoint_id="task-456",
        message="Aprovar mudança?",
        context={},
        status="pending",
        channel="email",
        sent_at=datetime.now(UTC),
        retry_count=0,
        max_retries=3,
        attempted_channels=[],
        fallback_channel=None,
        timeout_seconds=3600,
    )


class TestEmailChannelDisabled:
    """Email desligado por padrão (ENABLE_EMAIL_NOTIFICATIONS=false)."""

    @pytest.mark.asyncio
    async def test_email_not_sent_when_disabled(self, approval: ApprovalRequest) -> None:
        """Quando ENABLE_EMAIL_NOTIFICATIONS=false, não envia (no-op)."""
        channel = EmailChannel()

        with patch.object(settings, "enable_email_notifications", False):
            # Não deve levantar exceção, não deve chamar SMTP.
            with patch("app.notifications.email.smtplib.SMTP") as mock_smtp:
                await channel.send(approval, response_url="/approvals/test")
                mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_not_sent_when_no_smtp_host(self, approval: ApprovalRequest) -> None:
        """Quando habilitado mas sem SMTP_HOST, não envia (no-op)."""
        channel = EmailChannel()

        with (
            patch.object(settings, "enable_email_notifications", True),
            patch.object(settings, "smtp_host", ""),
        ):
            with patch("app.notifications.email.smtplib.SMTP") as mock_smtp:
                await channel.send(approval)
                mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_channel_name(self) -> None:
        """O nome do canal é 'email'."""
        channel = EmailChannel()
        assert channel.name == "email"


class TestEmailChannelEnabled:
    """Email habilitado (ENABLE_EMAIL_NOTIFICATIONS=true)."""

    @pytest.mark.asyncio
    async def test_email_sent_when_enabled(self, approval: ApprovalRequest) -> None:
        """Quando habilitado e SMTP_HOST presente, envia."""
        channel = EmailChannel()

        with (
            patch.object(settings, "enable_email_notifications", True),
            patch.object(settings, "smtp_host", "smtp.example.com"),
            patch.object(settings, "smtp_port", 587),
            patch.object(settings, "smtp_user", "user"),
            patch.object(settings, "smtp_password", "pass"),
            patch.object(settings, "smtp_from", "admin@example.com"),
        ):
            with patch("app.notifications.email.smtplib.SMTP") as mock_smtp:
                mock_server = AsyncMock()
                mock_smtp.return_value.__enter__ = lambda s: mock_server
                mock_smtp.return_value.__exit__ = lambda s, *a: None
                mock_server.sendmail = lambda *a, **kw: None
                mock_server.starttls = lambda: None
                mock_server.login = lambda *a: None

                await channel.send(approval, response_url="/approvals/test")

                mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10.0)

    @pytest.mark.asyncio
    async def test_email_smtp_failure_raises(self, approval: ApprovalRequest) -> None:
        """Se SMTP falhar, levanta NotificationError."""
        channel = EmailChannel()

        with (
            patch.object(settings, "enable_email_notifications", True),
            patch.object(settings, "smtp_host", "smtp.example.com"),
            patch.object(settings, "smtp_port", 587),
            patch.object(settings, "smtp_user", "user"),
            patch.object(settings, "smtp_password", "pass"),
            patch.object(settings, "smtp_from", "admin@example.com"),
        ):
            with patch("app.notifications.email.smtplib.SMTP") as mock_smtp:
                mock_smtp.side_effect = ConnectionRefusedError("Connection refused")

                with pytest.raises(NotificationError) as exc_info:
                    await channel.send(approval)

                assert exc_info.value.channel == "email"
                assert "Connection refused" in exc_info.value.message
