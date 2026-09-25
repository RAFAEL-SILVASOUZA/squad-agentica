"""Testes de health do worker (dono: rt-worker, FASE 6)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_container_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
