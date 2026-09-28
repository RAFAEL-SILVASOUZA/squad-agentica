"""Tests for the auth module (FASE 3, auth-backend).

Covers:
- Registration (success, duplicate email 409)
- Login (correct, wrong password, wrong email)
- Refresh (valid, rotation, reuse detection)
- Token expired
- Protected route without token (401)
- New router without explicit dependency is still protected (global auth)
- Rate limiting on login (429)
- WebSocket token validation
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.app_setup import apply_global_auth
from app.auth.dependencies import validate_ws_token
from app.auth.jwt import create_access_token, create_refresh_token
from app.auth.rate_limiter import login_rate_limiter
from app.auth.refresh_store import refresh_store
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_app(test_engine) -> AsyncIterator[FastAPI]:
    """Create a test FastAPI app with the auth router and global auth dependency."""
    from app.api.auth import router as auth_router

    app = FastAPI()
    register_exception_handlers(app)

    # Override get_db to use the test engine.
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Include the auth router.
    app.include_router(auth_router, prefix="/api")

    # Apply global auth (opt-out protection).
    apply_global_auth(app)

    # Health endpoints (public).
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/health")
    async def api_health():
        return {"status": "ok"}

    yield app


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client for the test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def registered_user(test_engine) -> User:
    """Create a user directly in the DB for tests that need an existing user."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            name="Test User",
            password_hash=hash_password("testpass123"),
            owner_id=uuid.uuid4(),
        )
        user.owner_id = user.id
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def auth_headers(registered_user: User) -> dict[str, str]:
    """Valid auth headers for the registered user."""
    token = create_access_token(str(registered_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the rate limiter before each test."""
    login_rate_limiter.cleanup()
    yield
    login_rate_limiter.cleanup()


@pytest.fixture(autouse=True)
def _reset_refresh_store():
    """Reset the refresh store before each test."""
    refresh_store.cleanup()
    yield
    refresh_store.cleanup()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        """POST /api/auth/register creates a new user (201)."""
        resp = await client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "password": "password123", "name": "New User"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert data["name"] == "New User"
        assert "id" in data

    async def test_register_duplicate_email(self, client: AsyncClient, registered_user: User):
        """POST /api/auth/register with existing email returns 409."""
        resp = await client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": "password123", "name": "Dup"},
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "conflict"
        assert data["code"] == "email_already_exists"

    async def test_register_short_password(self, client: AsyncClient):
        """POST /api/auth/register with short password returns 422."""
        resp = await client.post(
            "/api/auth/register",
            json={"email": "short@example.com", "password": "short", "name": "Short"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_login_success(self, client: AsyncClient, registered_user: User):
        """POST /api/auth/login with correct credentials returns tokens."""
        resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "accessToken" in data
        assert "refreshToken" in data
        assert data["tokenType"] == "Bearer"
        assert data["expiresIn"] == settings.access_token_expire_minutes * 60

    async def test_login_wrong_password(self, client: AsyncClient, registered_user: User):
        """POST /api/auth/login with wrong password returns 401 (generic)."""
        resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"] == "unauthorized"
        assert data["code"] == "invalid_credentials"

    async def test_login_nonexistent_email(self, client: AsyncClient):
        """POST /api/auth/login with non-existent email returns 401 (same as wrong password)."""
        resp = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "whatever123"},
        )
        assert resp.status_code == 401
        data = resp.json()
        # Same generic error as wrong password (does not reveal email existence).
        assert data["error"] == "unauthorized"
        assert data["code"] == "invalid_credentials"

    async def test_login_rate_limit(self, client: AsyncClient, registered_user: User):
        """POST /api/auth/login rate limited after 5 attempts (429)."""
        # Make 5 requests (the limit).
        for _ in range(5):
            resp = await client.post(
                "/api/auth/login",
                json={"email": "test@example.com", "password": "wrongpass"},
            )
            assert resp.status_code == 401

        # 6th request should be rate limited.
        resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"] == "rate_limited"
        assert data["code"] == "rate_limited"
        assert "retryAfter" in data["details"]


    async def test_login_rate_limit_is_per_account(
        self, client: AsyncClient, registered_user: User
    ):
        """Logins chegam todos do IP do portal: o limite de uma conta não bloqueia outra."""
        for _ in range(6):
            await client.post(
                "/api/auth/login",
                json={"email": "attacker-target@example.com", "password": "wrongpass"},
            )
        resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"},
        )
        assert resp.status_code == 200

# ---------------------------------------------------------------------------
# Refresh tests
# ---------------------------------------------------------------------------


class TestRefresh:
    async def test_refresh_success(self, client: AsyncClient, registered_user: User):
        """POST /api/auth/refresh with valid token returns new tokens."""
        # First login to get a refresh token.
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"},
        )
        refresh_token = login_resp.json()["refreshToken"]

        # Use the refresh token.
        resp = await client.post(
            "/api/auth/refresh",
            json={"refreshToken": refresh_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "accessToken" in data
        assert "refreshToken" in data
        # New refresh token should be different (rotation).
        assert data["refreshToken"] != refresh_token

    async def test_refresh_reuse_detected(self, client: AsyncClient, registered_user: User):
        """Reusing an already-rotated refresh token returns 401."""
        # Login to get refresh token.
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"},
        )
        old_refresh = login_resp.json()["refreshToken"]

        # First rotation (valid).
        resp1 = await client.post(
            "/api/auth/refresh",
            json={"refreshToken": old_refresh},
        )
        assert resp1.status_code == 200

        # Reuse the old token (should fail).
        resp2 = await client.post(
            "/api/auth/refresh",
            json={"refreshToken": old_refresh},
        )
        assert resp2.status_code == 401
        data = resp2.json()
        assert data["code"] == "refresh_token_reused"

    async def test_refresh_survives_store_loss(self, client: AsyncClient, registered_user: User):
        """Store em memória some no restart do orchestrator; o token válido segue aceito."""
        from app.auth.refresh_store import refresh_store

        login = await client.post(
            "/api/auth/login", json={"email": "test@example.com", "password": "testpass123"}
        )
        refresh_store._tokens.clear()  # simula restart
        resp = await client.post(
            "/api/auth/refresh", json={"refreshToken": login.json()["refreshToken"]}
        )
        assert resp.status_code == 200

    async def test_refresh_invalid_token(self, client: AsyncClient):
        """POST /api/auth/refresh with invalid token returns 401."""
        resp = await client.post(
            "/api/auth/refresh",
            json={"refreshToken": "invalid.token.here"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["code"] == "invalid_refresh_token"

    async def test_refresh_with_access_token_rejected(
        self, client: AsyncClient, registered_user: User
    ):
        """Using an access token as refresh token is rejected (type mismatch)."""
        access_token = create_access_token(str(registered_user.id))
        resp = await client.post(
            "/api/auth/refresh",
            json={"refreshToken": access_token},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token expiration tests
# ---------------------------------------------------------------------------


class TestTokenExpiration:
    async def test_expired_access_token_rejected(self, client: AsyncClient, registered_user: User):
        """An expired access token is rejected with 401."""
        # Create a token that expired 1 minute ago.
        now = datetime.now(UTC)
        payload = {
            "sub": str(registered_user.id),
            "typ": "access",
            "iat": now - timedelta(minutes=16),
            "exp": now - timedelta(minutes=1),
            "jti": str(uuid.uuid4()),
        }
        expired_token = jwt.encode(
            payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )

        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["code"] == "not_authenticated"


# ---------------------------------------------------------------------------
# Protected route tests
# ---------------------------------------------------------------------------


class TestProtectedRoutes:
    async def test_me_without_token(self, client: AsyncClient):
        """GET /api/auth/me without token returns 401."""
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"] == "unauthorized"
        assert data["code"] == "not_authenticated"

    async def test_me_with_valid_token(self, client: AsyncClient, auth_headers: dict):
        """GET /api/auth/me with valid token returns user info."""
        resp = await client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"

    async def test_new_router_is_protected_by_default(self, test_engine, registered_user: User):
        """A new router without explicit auth dependency is still protected (global auth)."""
        from app.api.auth import router as auth_router

        app = FastAPI()
        register_exception_handlers(app)

        factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        # Include auth router.
        app.include_router(auth_router, prefix="/api")

        # Create a NEW router with NO explicit auth dependency.
        new_router = APIRouter(prefix="/new-resource", tags=["new"])

        @new_router.get("/items")
        async def list_items():
            return {"items": []}

        app.include_router(new_router, prefix="/api")

        # Apply global auth.
        apply_global_auth(app)

        # Health endpoints.
        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.get("/api/health")
        async def api_health():
            return {"status": "ok"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # New route without token -> 401.
            resp = await c.get("/api/new-resource/items")
            assert resp.status_code == 401

            # New route with valid token -> 200.
            token = create_access_token(str(registered_user.id))
            resp = await c.get(
                "/api/new-resource/items",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"items": []}

    async def test_public_paths_are_exempt(self, client: AsyncClient):
        """Public paths (health, auth endpoints) work without a token."""
        # Health checks.
        resp = await client.get("/health")
        assert resp.status_code == 200

        resp = await client.get("/api/health")
        assert resp.status_code == 200

        # Auth endpoints (login doesn't need a token).
        resp = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "whatever123"},
        )
        # Should be 401 (invalid credentials), NOT 401 (not authenticated by global).
        # Both are 401 but the code differs.
        assert resp.status_code == 401
        assert resp.json()["code"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# WebSocket token validation tests
# ---------------------------------------------------------------------------


class TestWebSocketValidation:
    async def test_validate_ws_token_valid(self, registered_user: User):
        """validate_ws_token accepts a valid access token."""
        token = create_access_token(str(registered_user.id))
        payload = validate_ws_token(token)
        assert payload["sub"] == str(registered_user.id)
        assert payload["typ"] == "access"

    async def test_validate_ws_token_invalid(self):
        """validate_ws_token rejects an invalid token."""
        from app.core.errors import AppError

        with pytest.raises(AppError) as exc_info:
            validate_ws_token("invalid.token.here")
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "not_authenticated"

    async def test_validate_ws_token_refresh_rejected(self, registered_user: User):
        """validate_ws_token rejects a refresh token (wrong type)."""
        from app.core.errors import AppError

        token = create_refresh_token(str(registered_user.id))
        with pytest.raises(AppError) as exc_info:
            validate_ws_token(token)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# JWT unit tests
# ---------------------------------------------------------------------------


class TestJWT:
    def test_access_token_claims(self, registered_user: User):
        """Access token has correct claims."""
        from app.auth.jwt import validate_access_token

        token = create_access_token(str(registered_user.id))
        payload = validate_access_token(token)
        assert payload["sub"] == str(registered_user.id)
        assert payload["typ"] == "access"
        assert "iat" in payload
        assert "exp" in payload
        assert "jti" in payload

    def test_refresh_token_claims(self, registered_user: User):
        """Refresh token has correct claims."""
        from app.auth.jwt import validate_refresh_token

        token = create_refresh_token(str(registered_user.id))
        payload = validate_refresh_token(token)
        assert payload["sub"] == str(registered_user.id)
        assert payload["typ"] == "refresh"
        assert "iat" in payload
        assert "exp" in payload
        assert "jti" in payload

    def test_access_token_rejected_as_refresh(self, registered_user: User):
        """An access token cannot be validated as a refresh token."""
        from jose import JWTError

        from app.auth.jwt import validate_refresh_token

        token = create_access_token(str(registered_user.id))
        with pytest.raises(JWTError):
            validate_refresh_token(token)

    def test_refresh_token_rejected_as_access(self, registered_user: User):
        """A refresh token cannot be validated as an access token."""
        from jose import JWTError

        from app.auth.jwt import validate_access_token

        token = create_refresh_token(str(registered_user.id))
        with pytest.raises(JWTError):
            validate_access_token(token)
