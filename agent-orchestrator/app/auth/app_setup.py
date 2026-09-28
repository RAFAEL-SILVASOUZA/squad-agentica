"""Global auth dependency registration.

Dono: auth-backend (FASE 3). Contrato §5:
- Proteção opt-out: toda rota exige usuário exceto PUBLIC_PATHS.
- Um router novo criado por outro nó nasce protegido.

Usage in main.py (one line, owned by infra-docker):
    from app.auth.app_setup import apply_global_auth
    apply_global_auth(app)
"""

from __future__ import annotations

from fastapi import FastAPI


def apply_global_auth(app: FastAPI) -> None:
    """Register the global auth dependency on the FastAPI app.

    This makes every route require authentication by default (opt-out model).
    Routes listed in PUBLIC_PATHS are exempt.

    Uses a middleware to ensure all routes (including those from included
    routers) are protected.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Skip public paths.
            from app.auth.dependencies import PUBLIC_PATHS

            if request.url.path in PUBLIC_PATHS:
                return await call_next(request)

            # A ponte interna exige o token do worker no próprio router.
            if request.url.path.startswith("/internal/mcp/"):
                return await call_next(request)

            # Validate the Bearer token.
            from app.auth.dependencies import _bearer

            credentials = await _bearer(request)
            if credentials is None or not credentials.credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "code": "not_authenticated"},
                )

            # Validate the token.
            from jose import JWTError

            from app.auth.jwt import validate_access_token

            try:
                validate_access_token(credentials.credentials)
            except JWTError:
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "code": "not_authenticated"},
                )

            return await call_next(request)

    app.add_middleware(AuthMiddleware)
