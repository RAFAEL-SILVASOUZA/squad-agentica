"""Email notification channel (SMTP).

Dono: hitl-notification (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md §10 (email só se simples, desligado por padrão).
- PLANO-BACKEND.md §2.21 (email = template SMTP, só se ENABLE_EMAIL_NOTIFICATIONS=true).
- D7 §7.6 (template com link para o portal, SMTP via env).
- Spec 4.5 (channel: "email").

Desligado por padrão: ``ENABLE_EMAIL_NOTIFICATIONS=false``. Quando desligado,
o canal loga e ignora (nunca quebra o fluxo). Quando ligado, envia via SMTP
com template simples contendo link para o portal.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.db.models import ApprovalRequest
from app.notifications.inapp import NotificationError
from app.notifications.interface import NotificationChannel

logger = logging.getLogger(__name__)

# Timeout para conexão SMTP (segundos).
SMTP_TIMEOUT = 10.0


class EmailChannel:
    """Canal de email via SMTP.

    V1: desligado por padrão (``ENABLE_EMAIL_NOTIFICATIONS=false``).
    Quando desligado, ``send`` loga e retorna sem erro (não quebra o fluxo).
    Quando ligado, envia um email com template simples + link para o portal.
    """

    name: NotificationChannel = "email"

    async def send(self, approval: ApprovalRequest, response_url: str | None = None) -> None:
        """Envia email de notificação de aprovação.

        Se ``ENABLE_EMAIL_NOTIFICATIONS`` é False, loga e retorna (no-op).
        Se True, envia via SMTP (síncrono em thread para não bloquear o loop).

        Args:
            approval: A ApprovalRequest persistida.
            response_url: URL para o humano responder (portal).

        Raises:
            NotificationError: se o envio SMTP falhar (só quando habilitado).
        """
        if not settings.enable_email_notifications:
            logger.info(
                "email notification skipped (disabled by default)",
                extra={"approval_id": str(approval.id)},
            )
            return

        if not settings.smtp_host:
            logger.warning(
                "email notification skipped (SMTP_HOST not configured)",
                extra={"approval_id": str(approval.id)},
            )
            return

        # Monta o email.
        subject = f"Aprovação pendente: pipeline {approval.pipeline_id}"
        body = self._build_body(approval, response_url)

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._send_smtp, subject, body),
                timeout=SMTP_TIMEOUT,
            )
            logger.info(
                "email notification sent",
                extra={
                    "approval_id": str(approval.id),
                    "to": settings.smtp_from,  # V1: single-user, envia para o admin
                },
            )
        except TimeoutError:
            raise NotificationError("email", f"SMTP timeout after {SMTP_TIMEOUT}s") from None
        except Exception as exc:
            raise NotificationError("email", str(exc)) from exc

    def _build_body(self, approval: ApprovalRequest, response_url: str | None) -> str:
        """Monta o corpo do email (HTML simples)."""
        url = response_url or f"/approvals/{approval.id}"
        return f"""\
<html>
<body>
  <h2>Aprovação Pendente</h2>
  <p>Uma pipeline requer a sua aprovação.</p>
  <p><strong>Mensagem:</strong> {approval.message}</p>
  <p><strong>Pipeline:</strong> {approval.pipeline_id}</p>
  <p><strong>Run:</strong> {approval.run_id or "N/A"}</p>
  <p>
    <a href="{url}">Responder no Portal</a>
  </p>
</body>
</html>
"""

    def _send_smtp(self, subject: str, body: str) -> None:
        """Envia o email via SMTP (síncrono, roda em thread)."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        # V1 single-user: envia para o próprio admin (smtp_from).
        msg["To"] = settings.smtp_from
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, [settings.smtp_from], msg.as_string())
