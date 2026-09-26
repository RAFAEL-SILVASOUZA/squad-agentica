"""Suite de integracao da API contra o stack real (qa-integration).

Roda no HOST, contra o NGINX publico (``http://localhost``), com o stack
``docker compose -p squad-agentica`` de pe e ``LLM_PROVIDER=mock`` /
``EMBEDDING_PROVIDER=mock`` (contrato §4).

Cada cenario (modulo) cria o proprio usuario (e-mail ``qa-int-<uuid>@example.com``,
fixtures ``user``/``user_b`` com escopo de modulo, o que tambem respeita o rate
limit do login de 5/min por IP),
os proprios dados, e limpa no fim: recursos pela API quando ha endpoint de
DELETE; o usuario e o que sobrou dele (pipelines semeadas, runs, aprovacoes)
pelo ``DELETE FROM users`` (todas as FKs de owner sao ``ON DELETE CASCADE``).

Pipelines: o CRUD ``/api/pipelines`` nao existe (PENDENCIAS B1). Para exercitar
execucao, HITL, ciclo de vida e resiliencia a suite semeia a pipeline direto nas
tabelas ``pipelines``/``pipeline_nodes``/``pipeline_edges`` (Postgres publicado
em :15432), sempre no usuario do proprio teste. Os testes do CRUD em si
continuam falhando ate o B1 ser resolvido.

Variaveis (opcionais):
  QA_BASE_URL   default http://localhost   (use ``localhost``: no host Windows
                o 127.0.0.1:80 responde outro servico; o ::1:80 e o NGINX)
  QA_DB_DSN     default postgresql://agent_portal:agent_portal@localhost:15432/agent_portal
  QA_COMPOSE_PROJECT default squad-agentica
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.types.json import Jsonb

BASE_URL = os.environ.get("QA_BASE_URL", "http://localhost")
WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/ws"
DB_DSN = os.environ.get(
    "QA_DB_DSN", "postgresql://agent_portal:agent_portal@localhost:15432/agent_portal"
)
COMPOSE_PROJECT = os.environ.get("QA_COMPOSE_PROJECT", "squad-agentica")
PASSWORD = "QaIntegr4tion!"
EMAIL_PREFIX = "qa-int-"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=60)


def assert_envelope(resp: httpx.Response, status: int, code: str | None = None) -> dict:
    """Checa status e o envelope de erro do contrato §8."""
    assert resp.status_code == status, f"esperado {status}, obtido {resp.status_code}: {resp.text[:500]}"
    body = resp.json()
    assert isinstance(body, dict) and "error" in body and "code" in body, f"sem envelope: {body}"
    assert "traceback" not in resp.text.lower(), "stack trace vazou para o cliente"
    if code is not None:
        assert body["code"] == code, f"code esperado {code}, obtido {body['code']}"
    return body


def login(client: httpx.Client, email: str, password: str = PASSWORD) -> httpx.Response:
    """POST /api/auth/login respeitando o rate limit do login (5/min por IP).

    Todo o trafego do host chega ao orchestrator pelo mesmo IP (NGINX), entao o
    limite e compartilhado pela suite inteira: em 429 esperamos o retryAfter.
    """
    for _ in range(4):
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        if r.status_code != 429:
            return r
        wait = int(r.json().get("details", {}).get("retryAfter", 10)) + 1
        time.sleep(min(wait, 65))
    return r


@dataclass
class User:
    email: str
    id: str
    access: str
    refresh: str
    client: httpx.Client = field(repr=False)

    @property
    def h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access}"}

    def get(self, url: str, **kw: Any) -> httpx.Response:
        return self.client.get(url, headers=self.h, **kw)

    def post(self, url: str, **kw: Any) -> httpx.Response:
        return self.client.post(url, headers=self.h, **kw)

    def put(self, url: str, **kw: Any) -> httpx.Response:
        return self.client.put(url, headers=self.h, **kw)

    def delete(self, url: str, **kw: Any) -> httpx.Response:
        return self.client.delete(url, headers=self.h, **kw)


def new_user(label: str = "u") -> User:
    client = http()
    email = f"{EMAIL_PREFIX}{label}-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": f"QA {label}"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    r = login(client, email)
    assert r.status_code == 200, r.text
    tok = r.json()
    return User(email=email, id=uid, access=tok["accessToken"], refresh=tok["refreshToken"], client=client)


def purge_via_api(u: User) -> None:
    """Remove pela API o que tem copia no Garage (agentes), antes do cascade do banco."""
    for _ in range(20):
        items = u.get("/api/agents", params={"limit": 100}).json().get("items", [])
        if not items:
            return
        for a in items:
            u.delete(f"/api/agents/{a['id']}")


def delete_user(user_id: str) -> None:
    """Remove o usuario de teste e tudo dele (FKs ON DELETE CASCADE)."""
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


@pytest.fixture(scope="module")
def user() -> Iterator[User]:
    u = new_user("a")
    yield u
    purge_via_api(u)
    delete_user(u.id)


@pytest.fixture(scope="module")
def user_b() -> Iterator[User]:
    u = new_user("b")
    yield u
    purge_via_api(u)
    delete_user(u.id)


@pytest.fixture(scope="session", autouse=True)
def _stack_up() -> None:
    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=10)
    except httpx.HTTPError as exc:  # pragma: no cover - bloqueio de infra
        pytest.exit(f"stack fora do ar em {BASE_URL}: {exc}", returncode=3)
    if r.status_code != 200:  # pragma: no cover
        pytest.exit(f"/api/health respondeu {r.status_code}", returncode=3)


@pytest.fixture(scope="session", autouse=True)
def _sweep_leftovers() -> Iterator[None]:
    """Apaga usuarios qa-int-* que sobraram de execucoes interrompidas."""
    yield
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM users WHERE email LIKE %s", (f"{EMAIL_PREFIX}%@example.com",))


# ---------------------------------------------------------------------------
# Agentes
# ---------------------------------------------------------------------------


def agent_body(name: str, **over: Any) -> dict[str, Any]:
    body = {
        "name": name,
        "type": "custom",
        "description": "agente de teste qa-integration",
        "prompt": "Responda com o campo result.",
        "inputs": [{"name": "spec", "type": "document", "required": False}],
        "outputs": [{"name": "result", "type": "document", "required": True}],
        "actions": ["follow", "finalize"],
        "maxIterations": 5,
        "timeout": 60,
    }
    body.update(over)
    return body


def create_agent(u: User, name: str, **over: Any) -> dict[str, Any]:
    """Cria um agente com sufixo unico no nome (o usuario e compartilhado no modulo)."""
    r = u.post("/api/agents", json=agent_body(f"{name}-{uuid.uuid4().hex[:6]}", **over))
    assert r.status_code == 201, r.text
    return r.json()


def snapshot_of(agent: dict[str, Any]) -> dict[str, Any]:
    """AgentSnapshot congelado (spec 4.2) a partir do Agent da API."""
    return {
        "agentId": agent["id"],
        "version": 1,
        "name": agent["name"],
        "description": agent["description"],
        "prompt": agent["prompt"],
        "strategy": agent["strategy"],
        "skills": agent["skills"],
        "tools": agent["tools"],
        "mcpServers": agent["mcpServers"],
        "knowledge": agent["knowledge"],
        "integrations": agent["integrations"],
        "inputs": agent["inputs"],
        "outputs": agent["outputs"],
        "actions": agent["actions"],
        "model": agent["model"],
        "maxIterations": agent["maxIterations"],
        "timeout": agent["timeout"],
        "shellAccess": agent["shellAccess"],
    }


# ---------------------------------------------------------------------------
# Pipelines (semeadas no banco por causa do B1)
# ---------------------------------------------------------------------------


@dataclass
class SeededPipeline:
    id: str
    nodes: list[str]
    edges: list[str]


def seed_pipeline(
    owner_id: str,
    agents: list[dict[str, Any]],
    *,
    approval_on: int | None = None,
    reject_to_source: bool = False,
    name: str | None = None,
) -> SeededPipeline:
    """Semeia uma pipeline linear agents[0] -> agents[1] -> ...

    Cada par ganha uma flow edge e uma data edge (result -> spec).
    ``approval_on=i`` marca a flow edge i (entre o no i e o i+1) com
    ``requiresApproval`` e ``rejectTarget`` = no de origem se ``reject_to_source``.
    """
    pid = str(uuid.uuid4())
    node_ids = [str(uuid.uuid4()) for _ in agents]
    edges: list[str] = []
    with psycopg.connect(DB_DSN, autocommit=False) as conn:
        conn.execute(
            "INSERT INTO pipelines (id, owner_id, name, description, status, entry_node_id)"
            " VALUES (%s, %s, %s, %s, 'draft', %s)",
            (pid, owner_id, name or f"qa-pipe-{pid[:8]}", "semeada pela suite qa-integration", node_ids[0]),
        )
        for i, (nid, ag) in enumerate(zip(node_ids, agents, strict=True)):
            conn.execute(
                "INSERT INTO pipeline_nodes (id, pipeline_id, agent_id, position, label, agent_snapshot)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (nid, pid, ag["id"], Jsonb({"x": 100 * i, "y": 0}), ag["name"], Jsonb(snapshot_of(ag))),
            )
        for i in range(len(node_ids) - 1):
            src, tgt = node_ids[i], node_ids[i + 1]
            fid = str(uuid.uuid4())
            approval = approval_on == i
            conn.execute(
                "INSERT INTO pipeline_edges (id, pipeline_id, type, source, target, requires_approval,"
                " approval_channel, approval_message, reject_target)"
                " VALUES (%s, %s, 'flow', %s, %s, %s, %s, %s, %s)",
                (
                    fid, pid, src, tgt, approval,
                    "in-app" if approval else None,
                    "QA: aprovar a passagem?" if approval else None,
                    src if (approval and reject_to_source) else None,
                ),
            )
            did = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO pipeline_edges (id, pipeline_id, type, source, target, requires_approval, data_mapping)"
                " VALUES (%s, %s, 'data', %s, %s, false, %s)",
                (did, pid, src, tgt, Jsonb({"sourceOutput": "result", "targetInput": "spec"})),
            )
            edges += [fid, did]
        conn.commit()
    return SeededPipeline(id=pid, nodes=node_ids, edges=edges)


def db_query(sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        return list(conn.execute(sql, params).fetchall())


def wait_until(fn, timeout: float = 30.0, interval: float = 0.5, desc: str = "condicao"):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"timeout esperando {desc}; ultimo valor: {last!r}")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


class WsCollector:
    """Conecta em /api/ws?token= e coleta frames {channel, data} numa thread."""

    def __init__(self, token: str) -> None:
        from websockets.sync.client import connect

        self.frames: list[dict[str, Any]] = []
        self.raw: list[str] = []
        self._stop = threading.Event()
        self._ws = connect(f"{WS_URL}?token={token}", open_timeout=10)
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self._ws.recv(timeout=0.5)
            except TimeoutError:
                continue
            except Exception:
                return
            self.raw.append(msg if isinstance(msg, str) else msg.decode())
            try:
                self.frames.append(json.loads(self.raw[-1]))
            except ValueError:
                pass

    def of(self, channel: str, pipeline_id: str | None = None) -> list[dict[str, Any]]:
        out = []
        for f in self.frames:
            if f.get("channel") != channel:
                continue
            if pipeline_id and (f.get("data") or {}).get("pipelineId") != pipeline_id:
                continue
            out.append(f["data"])
        return out

    def close(self) -> None:
        self._stop.set()
        try:
            self._ws.close()
        except Exception:
            pass


@pytest.fixture
def ws_factory() -> Iterator:
    opened: list[WsCollector] = []

    def _make(token: str) -> WsCollector:
        c = WsCollector(token)
        opened.append(c)
        return c

    yield _make
    for c in opened:
        c.close()


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------


def compose(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-p", COMPOSE_PROJECT, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
