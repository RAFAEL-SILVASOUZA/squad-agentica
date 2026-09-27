"""Structured error envelope and FastAPI exception handlers.

Dono: infra-docker. Envelope do contrato §8:
    { "error": str, "code": str, "details"?: object }
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_response(
    status_code: int, error: str, code: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    """Build the standard error envelope response."""
    body: dict[str, Any] = {"error": error, "code": code}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


class AppError(Exception):
    """Base application error carrying the envelope fields."""

    def __init__(
        self, status_code: int, error: str, code: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.code = code
        self.details = details


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers that turn exceptions into the standard envelope."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.error, exc.code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # F13/B2: ``exc.errors()`` carrega ``ctx`` com objetos Python crus
        # (ex.: a ``ValueError`` lançada por um ``field_validator``), que a
        # serialização JSON da resposta não consegue converter e virava 500
        # (``Object of type ValueError is not JSON serializable``). Passamos
        # pelo ``jsonable_encoder`` para garantir um payload serializável.
        errors = jsonable_encoder(exc.errors())
        return error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unprocessable",
            "schema_validation",
            {"errors": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Nunca vaza stack trace para o cliente (contrato §8).
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "internal error", "internal_error"
        )
