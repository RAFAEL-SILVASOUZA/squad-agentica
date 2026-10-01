"""Middleware ASGI de autenticação para o servidor MCP.

Valida o token Bearer (JWT com typ="mcp") em cada request ao endpoint
/mcp/mcp. Verifica:
- Presença do header Authorization
- Assinatura e expiração do JWT (jwt.decode)
- typ == "mcp"
- aud == <mcp_base_url>/mcp/mcp
- jti não revogado (consulta ao banco)
- sub (user_id) existe no banco

Em caso de sucesso, injeta o User no contextvar ``current_user`` e
encaminha o request ao app ASGI interno (streamable HTTP do FastMCP).
"""

from __future__ import annotations

import uuid

from jose import JWTError, jwt
from sqlalchemy import select

from app.core.config import settings
from app.db.models import MCPOAuthToken, User
from app.db.session import async_session_factory
from app.mcp_server.context import current_user


def _resource_metadata() -> str:
    """URL do metadata de recurso protegido (RFC 9728)."""
    return f"{settings.mcp_base_url}/.well-known/oauth-protected-resource"


async def _send_401(send, resource_metadata: str) -> None:
    """Responde 401 com header WWW-Authenticate (RFC 6750 + RFC 9728)."""
    body = b'{"error":"unauthorized","code":"mcp_auth_failed"}'
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (
            b"www-authenticate",
            f'Bearer resource_metadata="{resource_metadata}", scope="mcp:full"'.encode(),
        ),
    ]
    await send({"type": "http.response.start", "status": 401, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def _extract_bearer_token(scope: dict) -> str | None:
    """Extrai o token Bearer do header Authorization no scope ASGI.

    Retorna None se o header não existir ou não for Bearer.
    """
    for key, value in scope.get("headers", []):
        if key == b"authorization":
            decoded = value.decode("latin-1")
            if decoded.startswith("Bearer "):
                return decoded[7:].strip()
            return None
    return None


class MCPAuthMiddleware:
    """Middleware ASGI puro de autenticação para o servidor MCP.

    Não usa BaseHTTPMiddleware (que não suporta streaming corretamente
    para o protocolo Streamable HTTP do MCP).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Só processa requests HTTP (ignora websocket e lifespan).
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extrai o token Bearer.
        token = _extract_bearer_token(scope)
        if token is None:
            await _send_401(send, _resource_metadata())
            return

        # Decodifica e valida o JWT (assinatura, exp, aud).
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                audience=f"{settings.mcp_base_url}/mcp/mcp",
            )
        except JWTError:
            await _send_401(send, _resource_metadata())
            return

        # Valida typ == "mcp".
        if payload.get("typ") != "mcp":
            await _send_401(send, _resource_metadata())
            return

        # Extrai jti e sub.
        jti = payload.get("jti")
        sub = payload.get("sub")
        if not jti or not sub:
            await _send_401(send, _resource_metadata())
            return

        # Consulta o banco: verifica revogação e carrega o usuário.
        try:
            async with async_session_factory() as session:
                # Verifica se o token foi revogado.
                result = await session.execute(
                    select(MCPOAuthToken.revoked_at).where(MCPOAuthToken.jti == jti)
                )
                revoked_at = result.scalar_one_or_none()
                if revoked_at is not None:
                    await _send_401(send, _resource_metadata())
                    return

                # Carrega o usuário.
                try:
                    user_id = uuid.UUID(sub)
                except (ValueError, AttributeError):
                    await _send_401(send, _resource_metadata())
                    return

                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    await _send_401(send, _resource_metadata())
                    return
        except Exception:
            # Falha de banco ou qualquer erro inesperado: 401.
            await _send_401(send, _resource_metadata())
            return

        # Injeta o usuário no contextvar e encaminha ao app interno.
        token_value = current_user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            current_user.reset(token_value)
