"""Testes do canal in-app de notificação.

Dono: hitl-notification (FASE 7).
Critérios de aceite (PLANO-BACKEND §2.21):
(a) in-app emite approval:new via publish.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import ApprovalRequest
from app.notifications.inapp import InAppChannel, NotificationError


@pytest.fixture
def approval() -> ApprovalRequest:
    """Cria uma ApprovalRequest em memória (sem banco)."""
    return ApprovalRequest(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        pipeline_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="approval_node_e1",
        checkpoint_id="task-123",
        message="Aprovar deploy?",
        context={"output": "resultado do agente"},
        status="pending",
        channel="in-app",
        sent_at=datetime.now(UTC),
        retry_count=0,
        max_retries=3,
        attempted_channels=[],
        fallback_channel=None,
        timeout_seconds=3600,
    )


class TestInAppChannel:
    """Testes do canal in-app (WebSocket approval:new)."""

    @pytest.mark.asyncio
    async def test_publish_called_with_correct_payload(self, approval: ApprovalRequest) -> None:
        """In-app publica approval:new com o payload do contrato §7."""
        channel = InAppChannel()

        with patch("app.notifications.inapp.ws_publish", new_callable=AsyncMock) as mock_publish:
            await channel.send(approval)

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            # Primeiro arg: owner_id (string).
            assert call_args[0][0] == str(approval.owner_id)
            # Segundo arg: canal.
            assert call_args[0][1] == "approval:new"
            # Terceiro arg: payload.
            payload = call_args[0][2]
            assert payload["approvalId"] == str(approval.id)
            assert payload["pipelineId"] == str(approval.pipeline_id)
            assert payload["runId"] == str(approval.run_id)
            assert payload["nodeId"] == "approval_node_e1"
            assert payload["message"] == "Aprovar deploy?"
            assert "at" in payload

    @pytest.mark.asyncio
    async def test_owner_isolation(self, approval: ApprovalRequest) -> None:
        """O evento é publicado para o owner_id correto (isolamento)."""
        channel = InAppChannel()
        expected_owner = str(approval.owner_id)

        with patch("app.notifications.inapp.ws_publish", new_callable=AsyncMock) as mock_publish:
            await channel.send(approval)

            # Verifica que o owner_id no publish é exatamente o da approval.
            assert mock_publish.call_args[0][0] == expected_owner

    @pytest.mark.asyncio
    async def test_publish_failure_raises_error(self, approval: ApprovalRequest) -> None:
        """Se o publish falhar, levanta NotificationError."""
        channel = InAppChannel()

        with patch(
            "app.notifications.inapp.ws_publish",
            new_callable=AsyncMock,
            side_effect=ConnectionError("WS disconnected"),
        ):
            with pytest.raises(NotificationError) as exc_info:
                await channel.send(approval)

            assert exc_info.value.channel == "in-app"
            assert "WS disconnected" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_run_id_none_handled(self, approval: ApprovalRequest) -> None:
        """Se run_id é None, o payload tem runId=None."""
        approval.run_id = None
        channel = InAppChannel()

        with patch("app.notifications.inapp.ws_publish", new_callable=AsyncMock) as mock_publish:
            await channel.send(approval)

            payload = mock_publish.call_args[0][2]
            assert payload["runId"] is None

    @pytest.mark.asyncio
    async def test_channel_name(self) -> None:
        """O nome do canal é 'in-app'."""
        channel = InAppChannel()
        assert channel.name == "in-app"
