"""Notification channels and delivery service.

Dono: hitl-notification (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md (C-01, §7, §10, §11.7)
- PLANO-BACKEND.md §2.21
- D7-human-in-the-loop.md §7.5-7.7
- Spec 4.5 (ApprovalRequest), 5.3 (HITL), 9.7 (WebSocket), 14 (risks)

Arquivos:
- interface.py: NotificationChannel type + NotificationChannel protocol.
- inapp.py: in-app channel (WebSocket approval:new).
- email.py: email channel (SMTP, disabled by default).
- teams.py: Teams stub (V2).
- slack.py: Slack stub (V2).
- service.py: notify_with_fallback (retry, timeout, fallback).
"""
