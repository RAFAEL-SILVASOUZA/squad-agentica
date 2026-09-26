"""Cenario 1 - Auth: registro, login, refresh, 401 sem token, rota nova protegida.

Fontes: contrato §5 e §8, GUIA-API-FRONTEND "Autenticacao", spec 14.1.
"""

from __future__ import annotations

import uuid

import pytest

from conftest import PASSWORD, assert_envelope, delete_user, http, login


@pytest.fixture
def fresh():
    client = http()
    email = f"qa-int-auth-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": "QA Auth"})
    assert r.status_code == 201, r.text
    body = r.json()
    yield client, email, body
    delete_user(body["id"])


def test_register_returns_user_without_password(fresh):
    _, email, body = fresh
    assert body["email"] == email
    assert set(body) >= {"id", "email", "name"}
    assert not any("password" in k.lower() for k in body), body
    uuid.UUID(body["id"])


def test_register_duplicate_email_409(fresh):
    client, email, _ = fresh
    r = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": "dup"})
    assert_envelope(r, 409)


def test_register_invalid_payload_is_enveloped_422(fresh):
    client, _, _ = fresh
    r = client.post("/api/auth/register", json={"email": "sem-arroba", "password": "x", "name": ""})
    # Contrato §8: 422 {error: "unprocessable", code: <schema_validation>, details.errors}
    body = assert_envelope(r, 422)
    assert "errors" in body.get("details", {}), body


def test_login_me_refresh_rotation(fresh):
    client, email, reg = fresh
    r = login(client, email)
    assert r.status_code == 200, r.text
    tok = r.json()
    assert tok["tokenType"] == "Bearer" and tok["expiresIn"] > 0
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok['accessToken']}"})
    assert me.status_code == 200 and me.json()["id"] == reg["id"]

    r2 = client.post("/api/auth/refresh", json={"refreshToken": tok["refreshToken"]})
    assert r2.status_code == 200, r2.text
    tok2 = r2.json()
    assert tok2["refreshToken"] != tok["refreshToken"]
    me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok2['accessToken']}"})
    assert me2.status_code == 200

    # Rotacao: o refresh antigo nao pode ser reutilizado (contrato §5).
    r3 = client.post("/api/auth/refresh", json={"refreshToken": tok["refreshToken"]})
    assert_envelope(r3, 401)


def test_refresh_rejects_access_token(fresh):
    client, email, _ = fresh
    tok = login(client, email).json()
    r = client.post("/api/auth/refresh", json={"refreshToken": tok["accessToken"]})
    assert_envelope(r, 401)


def test_login_wrong_password_generic_401(fresh):
    client, email, _ = fresh
    r_wrong_pw = login(client, email, "senha-errada-123")
    r_no_user = login(client, f"nao-existe-{uuid.uuid4().hex[:6]}@example.com", "senha-errada-123")
    b1 = assert_envelope(r_wrong_pw, 401)
    b2 = assert_envelope(r_no_user, 401)
    # Mensagem generica: nao revela se o e-mail existe.
    assert b1 == b2


def test_login_seed_admin_email_without_tld_does_not_500():
    """PENDENCIAS B2: e-mail do seed (admin@local) nao pode derrubar o login com 500."""
    client = http()
    r = login(client, "admin@local", "senha-qualquer-errada")
    assert r.status_code != 500, f"B2 ainda presente: {r.status_code} {r.text}"
    assert r.status_code in (401, 422), r.text


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/auth/me"),
        ("GET", "/api/agents"),
        ("GET", "/api/skills"),
        ("GET", "/api/skills/builtins"),
        ("GET", "/api/tools"),
        ("GET", "/api/mcp-servers"),
        ("GET", "/api/knowledge"),
        ("GET", "/api/integrations"),
        ("GET", "/api/approvals"),
        ("POST", f"/api/pipelines/{uuid.uuid4()}/execute"),
        ("GET", f"/api/pipelines/{uuid.uuid4()}/runs"),
    ],
)
def test_protected_routes_401_without_token(method, path):
    r = http().request(method, path)
    assert_envelope(r, 401, "not_authenticated")


def test_unknown_new_route_is_protected_by_default():
    """Protecao opt-out: rota que nenhum no declarou responde 401, nao 404."""
    r = http().get(f"/api/qa-rota-nova-{uuid.uuid4().hex[:6]}")
    assert_envelope(r, 401, "not_authenticated")


def test_openapi_and_docs_protected():
    c = http()
    for p in ("/api/openapi.json", "/api/docs"):
        r = c.get(p)
        assert r.status_code == 401, (p, r.status_code)


def test_invalid_and_malformed_tokens_401():
    c = http()
    for hdr in ("Bearer abc.def.ghi", "Bearer", "Basic Zm9vOmJhcg=="):
        r = c.get("/api/agents", headers={"Authorization": hdr})
        assert_envelope(r, 401)
