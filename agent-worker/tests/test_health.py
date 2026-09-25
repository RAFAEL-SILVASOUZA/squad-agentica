"""Testes de health do worker (scaffold, dono: infra-docker)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_container_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_execute_stub() -> None:
    """O scaffold responde 501 em /execute (rt-worker implementa depois)."""
    body = {"agentId": "x", "nodeId": "y", "inputs": {}, "timeout": 60}
    resp = client.post("/execute", json=body)
    assert resp.status_code == 501
    assert resp.json()["code"] == "execute_not_implemented"
