"""Helper de banco para a suíte E2E (nó qa-e2e).

A suíte E2E roda em Node (Playwright), mas precisa semear pipelines e aprovações
direto no Postgres porque o CRUD de pipeline e o HITL estão quebrados (F9 e
F1/F6 do relatório de integração). Este script é o ponto único de acesso ao
banco da suíte: recebe comandos em JSON no stdin e devolve JSON no stdout.

Uso:  python e2e/tools/db.py <comando> [args-json]
      python e2e/tools/db.py delete-user '<id>'
      python e2e/tools/db.py create-agent '<ownerId>' '<name>' [json-overrides]
      python e2e/tools/db.py seed-pipeline '{"ownerId":"...","agents":[{"id":"...","name":"..."}],"approvalOn":0,"rejectToSource":true}'
      python e2e/tools/db.py seed-approval '{"ownerId":"...","pipelineId":"...","nodeId":"n1","message":"..."}'
      python e2e/tools/db.py delete-pipeline '<id>'
      python e2e/tools/db.py query '<sql>' '<json-params>'
      python e2e/tools/db.py count-users '<email-like>'

O DSN vem da variável E2E_DB_DSN (default: postgresql://agent_portal:agent_portal@localhost:15432/agent_portal).
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

DB_DSN = os.environ.get(
    "E2E_DB_DSN",
    "postgresql://agent_portal:agent_portal@localhost:15432/agent_portal",
)


def _out(payload: Any) -> None:
    print(json.dumps(payload, default=str, ensure_ascii=False))


def _snapshot(agent: dict[str, Any]) -> dict[str, Any]:
    """AgentSnapshot minimal que o front/monitor aceitam (espelha conftest)."""
    return {
        "agentId": agent["id"],
        "version": 1,
        "name": agent["name"],
        "description": agent.get("description", "qa-e2e"),
        "prompt": agent.get("prompt", "Responda com o campo result."),
        "strategy": "react",
        "skills": agent.get("skills", []),
        "tools": agent.get("tools", []),
        "mcpServers": agent.get("mcpServers", []),
        "knowledge": agent.get("knowledge", []),
        "integrations": agent.get("integrations", []),
        "inputs": agent.get(
            "inputs", [{"name": "spec", "type": "document", "required": False}]
        ),
        "outputs": agent.get(
            "outputs", [{"name": "result", "type": "document", "required": True}]
        ),
        "actions": agent.get("actions", ["follow", "finalize"]),
        "model": "gpt-4o",
        "maxIterations": agent.get("maxIterations", 5),
        "timeout": agent.get("timeout", 60),
        "shellAccess": False,
    }


def cmd_query(sql: str, params_json: str) -> None:
    params = json.loads(params_json) if params_json else ()
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        rows = conn.execute(sql, params).fetchall()
        _out([list(r) for r in rows])


def cmd_create_agent(owner_id: str, name: str, overrides_json: str | None) -> None:
    over = json.loads(overrides_json) if overrides_json else {}
    agent_id = str(uuid.uuid4())
    row = dict(
        id=agent_id,
        owner_id=owner_id,
        name=name,
        type="custom",
        description="qa-e2e agent",
        prompt="Responda com o campo result.",
        strategy="react",
        skills=[],
        tools=[],
        mcpServers=[],
        knowledge=[],
        integrations=[],
        inputs=[{"name": "spec", "type": "document", "required": False}],
        outputs=[{"name": "result", "type": "document", "required": True}],
        actions=["follow", "finalize"],
        model="gpt-4o",
        max_iterations=5,
        timeout=60,
        shell_access=False,
    )
    row.update(over)
    cols = list(row.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    sql = (
        f"INSERT INTO agents ({', '.join(chr(34) + c + chr(34) for c in cols)}) VALUES ({placeholders}) "
        "RETURNING id, name, type, description, inputs, outputs, actions, max_iterations"
    )
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        r = conn.execute(sql, [Jsonb(row[c]) if isinstance(row[c], (list, dict)) else row[c] for c in cols]).fetchone()
        _out(dict(zip(['id', 'name', 'type', 'description', 'inputs', 'outputs', 'actions', 'maxIterations'], r)))


def cmd_seed_pipeline(spec: dict[str, Any]) -> None:
    """Semeia uma pipeline linear. spec:
       {ownerId, name?, agents:[{id,name,...snapshot fields}], approvalOn?:int, rejectToSource?:bool}
       approvalOn=i marca a flow edge i (entre nó i e i+1) com requiresApproval.
    """
    owner_id = spec["ownerId"]
    agents = spec["agents"]
    pid = str(uuid.uuid4())
    node_ids = [str(uuid.uuid4()) for _ in agents]
    approval_on = spec.get("approvalOn")
    reject_to_source = bool(spec.get("rejectToSource", False))
    name = spec.get("name") or f"qa-e2e-{pid[:8]}"
    with psycopg.connect(DB_DSN, autocommit=False) as conn:
        conn.execute(
            "INSERT INTO pipelines (id, owner_id, name, description, status, entry_node_id) "
            "VALUES (%s,%s,%s,%s,'draft',%s)",
            (pid, owner_id, name, "semeada pela suite qa-e2e", node_ids[0]),
        )
        for i, (nid, ag) in enumerate(zip(node_ids, agents, strict=True)):
            conn.execute(
                "INSERT INTO pipeline_nodes (id, pipeline_id, agent_id, position, label, agent_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (nid, pid, ag["id"], Jsonb({"x": 420 * i, "y": 0}), ag["name"], Jsonb(_snapshot(ag))),
            )
        for i in range(len(node_ids) - 1):
            src, tgt = node_ids[i], node_ids[i + 1]
            fid = str(uuid.uuid4())
            approval = approval_on == i
            conn.execute(
                "INSERT INTO pipeline_edges (id, pipeline_id, type, source, target, requires_approval, "
                "approval_channel, approval_message, reject_target) VALUES (%s,%s,'flow',%s,%s,%s,%s,%s,%s)",
                (
                    fid, pid, src, tgt, approval,
                    "in-app" if approval else None,
                    "QA E2E: aprovar a passagem?" if approval else None,
                    src if (approval and reject_to_source) else None,
                ),
            )
            did = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO pipeline_edges (id, pipeline_id, type, source, target, requires_approval, data_mapping) "
                "VALUES (%s,%s,'data',%s,%s,false,%s)",
                (did, pid, src, tgt, Jsonb({"sourceOutput": "result", "targetInput": "spec"})),
            )
        conn.commit()
        _out({"id": pid, "nodes": node_ids, "name": name, "entryNodeId": node_ids[0]})


def cmd_seed_approval(spec: dict[str, Any]) -> None:
    """Cria uma ApprovalRequest pendente (workaround F1/F6 para exercitar a UI)."""
    owner_id = spec["ownerId"]
    pipeline_id = spec["pipelineId"]
    node_id = spec["nodeId"]
    message = spec.get("message", "Aprovar a passagem?")
    aid = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO approval_requests (id, owner_id, pipeline_id, run_id, node_id, agent_id, "
            "checkpoint_id, message, context, status, channel, sent_at, retry_count, max_retries, attempted_channels, timeout_seconds) "
            "VALUES (%s,%s,%s,%s,%s,NULL,%s,%s,%s,'pending','in-app',now(),0,3,'{}',600)",
            (
                aid, owner_id, pipeline_id, run_id, node_id,
                spec.get("checkpointId", str(uuid.uuid4())), message,
                Jsonb({"output": "resultado do nó anterior (QA E2E)"}),
            ),
        )
        _out({"id": aid, "runId": run_id, "pipelineId": pipeline_id, "nodeId": node_id})


def cmd_delete_pipeline(pipeline_id: str) -> None:
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM pipelines WHERE id=%s", (pipeline_id,))
        _out({"deleted": pipeline_id})


def cmd_delete_user(user_id: str) -> None:
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM users WHERE id=%s AND email LIKE 'qa-e2e-%%'", (user_id,))
        _out({"deleted": user_id})


def cmd_count_users(email_like: str) -> None:
    with psycopg.connect(DB_DSN, autocommit=True) as conn:
        n = conn.execute("SELECT count(*) FROM users WHERE email LIKE %s", (email_like,)).fetchone()[0]
        _out(n)


def main() -> None:
    if len(sys.argv) < 2:
        _out({"error": "no command"})
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == "query":
        cmd_query(args[0], args[1] if len(args) > 1 else "")
    elif cmd == "create-agent":
        cmd_create_agent(args[0], args[1], args[2] if len(args) > 2 else None)
    elif cmd == "seed-pipeline":
        cmd_seed_pipeline(json.loads(args[0]))
    elif cmd == "seed-approval":
        cmd_seed_approval(json.loads(args[0]))
    elif cmd == "delete-pipeline":
        cmd_delete_pipeline(args[0])
    elif cmd == "delete-user":
        cmd_delete_user(args[0])
    elif cmd == "count-users":
        cmd_count_users(args[0])
    else:
        _out({"error": f"unknown command {cmd}"})
        sys.exit(2)


if __name__ == "__main__":
    main()
