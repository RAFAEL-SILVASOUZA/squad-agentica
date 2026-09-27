"""Remove segredos de query string dos logs (contrato §8: nunca logar token).

O WebSocket autentica por ``?token=<JWT>`` e o uvicorn registra o caminho com a
query string (``"WebSocket /api/ws?token=..." [accepted]`` no logger
``uvicorn.error``; requisições HTTP no ``uvicorn.access``).
"""

from __future__ import annotations

import logging
import re

_SECRET_PARAM = re.compile(r"([?&](?:token|access_token)=)[^&\s\"']+", re.IGNORECASE)
REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    return _SECRET_PARAM.sub(rf"\g<1>{REDACTED}", text)


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


def install_log_redaction(
    logger_names: tuple[str, ...] = ("uvicorn.error", "uvicorn.access"),
) -> None:
    for name in logger_names:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactSecretsFilter) for f in logger.filters):
            logger.addFilter(RedactSecretsFilter())
