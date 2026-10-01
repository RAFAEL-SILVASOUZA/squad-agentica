"""Pydantic schemas for the auth API (camelCase per contract §8).

Dono: auth-backend (FASE 3).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Simple email regex (RFC 5322 simplified; no email-validator dependency).
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _validate_email(v: str) -> str:
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid email address")
    return v


class RegisterRequest(BaseModel):
    """POST /api/auth/register body."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "email": "admin@local",
        "password": "s3cret!",
        "name": "Admin",
    }})

    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validate_email(v)


class LoginRequest(BaseModel):
    """POST /api/auth/login body."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "email": "admin@local",
        "password": "s3cret!",
    }})

    email: str = Field(max_length=320)
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validate_email(v)


class RefreshRequest(BaseModel):
    """POST /api/auth/refresh body."""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"refreshToken": "eyJhbGciOi..."}},
    )

    refresh_token: str = Field(alias="refreshToken")


class TokenResponse(BaseModel):
    """Response for login and refresh."""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {
            "accessToken": "eyJhbGciOi...",
            "refreshToken": "eyJhbGciOi...",
            "tokenType": "Bearer",
            "expiresIn": 900,
        }},
    )

    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    token_type: str = Field(default="Bearer", alias="tokenType")
    expires_in: int = Field(alias="expiresIn")


class UserResponse(BaseModel):
    """GET /api/auth/me response."""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {
            "id": "uuid",
            "email": "admin@local",
            "name": "Admin",
        }},
    )

    id: str
    email: str
    name: str


class PreferencesRequest(BaseModel):
    """PUT /api/auth/preferences body (adendo 8).

    Campo ausente = não mexer; ``null`` = limpar a escolha. O endpoint usa
    ``model_fields_set`` para distinguir os dois casos (o default de ``None``
    sozinho não permite).
    """

    model_config = ConfigDict(populate_by_name=True)

    default_llm_integration_id: str | None = Field(
        default=None, alias="defaultLlmIntegrationId"
    )
    default_embedding_integration_id: str | None = Field(
        default=None, alias="defaultEmbeddingIntegrationId"
    )


class PreferencesResponse(BaseModel):
    """GET/PUT /api/auth/preferences response (adendo 8)."""

    model_config = ConfigDict(populate_by_name=True)

    default_llm_integration_id: str | None = Field(
        default=None, alias="defaultLlmIntegrationId"
    )
    default_embedding_integration_id: str | None = Field(
        default=None, alias="defaultEmbeddingIntegrationId"
    )
