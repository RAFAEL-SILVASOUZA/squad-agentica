"""MCP server validator: valida config de conexao.

Dono: be-skills (FASE 4). Spec 6.7:
- stdio: command obrigatorio.
- sse/http: url obrigatorio.
- env: dict de variaveis de ambiente (secrets ref, nunca valor em claro).
"""

from __future__ import annotations

from typing import Any


def validate_mcp_config(
    transport: str,
    command: str | None = None,
    url: str | None = None,
    env: dict[str, Any] | None = None,
) -> list[str]:
    """Valida a configuracao de conexao de um servidor MCP.

    Retorna uma lista de erros (vazia se valido).
    """
    errors: list[str] = []

    # Transport valid.
    if transport not in ("stdio", "sse", "http"):
        errors.append(f"Invalid transport: {transport}. Must be 'stdio', 'sse' or 'http'")
        return errors

    # stdio requires command.
    if transport == "stdio":
        if not command or not command.strip():
            errors.append("command is required when transport is 'stdio'")
        elif len(command) > 500:
            errors.append("command must be at most 500 characters")

    # sse/http requires url.
    if transport in ("sse", "http"):
        if not url or not url.strip():
            errors.append(f"url is required when transport is '{transport}'")
        elif not (url.startswith("http://") or url.startswith("https://")):
            errors.append(f"url must start with http:// or https:// (got: {url})")
        elif len(url) > 500:
            errors.append("url must be at most 500 characters")

    # env validation.
    if env is not None:
        if not isinstance(env, dict):
            errors.append("env must be a dictionary")
        else:
            for key, value in env.items():
                if not isinstance(key, str) or not key:
                    errors.append(f"env keys must be non-empty strings (got: {key!r})")
                if not isinstance(value, str):
                    errors.append(f"env values must be strings (key: {key!r})")

    return errors
