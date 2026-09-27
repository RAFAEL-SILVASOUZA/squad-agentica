"""F16: o JWT da query string do WebSocket não chega aos logs do uvicorn."""

from __future__ import annotations

import logging

from app.core.log_redaction import REDACTED, RedactSecretsFilter, redact

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig-_part"


def test_redact_token_param():
    assert redact(f"/api/ws?token={JWT}") == f"/api/ws?token={REDACTED}"
    assert redact(f"/x?a=1&access_token={JWT}&b=2") == f"/x?a=1&access_token={REDACTED}&b=2"
    assert redact("/api/agents?page=1") == "/api/agents?page=1"


def test_filter_redacts_uvicorn_websocket_record():
    record = logging.LogRecord(
        "uvicorn.error", logging.INFO, __file__, 1,
        '%s - "WebSocket %s" [accepted]', ("('1.2.3.4', 5)", f"/api/ws?token={JWT}"), None,
    )
    assert RedactSecretsFilter().filter(record)
    assert JWT not in record.getMessage()
    assert REDACTED in record.getMessage()


def test_installed_on_uvicorn_loggers():
    import app.main  # noqa: F401  (instala o filtro no import)

    for name in ("uvicorn.error", "uvicorn.access"):
        assert any(isinstance(f, RedactSecretsFilter) for f in logging.getLogger(name).filters)
