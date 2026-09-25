"""Testes de health do orchestrator (scaffold, dono: infra-docker)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_container_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_health() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
