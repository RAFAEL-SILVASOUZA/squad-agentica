"""F18: a saída do agente sai pela porta declarada, não pela chave ``output``."""

from __future__ import annotations

import json

from app.worker import AgentSnapshot, _parse_output


def _snapshot(outputs: list[dict]) -> AgentSnapshot:
    return AgentSnapshot(
        id="a1", name="Writer", type="Dev", description="", prompt="p", strategy="",
        model="m", max_iterations=1, timeout=30, shell_access=False,
        outputs=outputs, actions=["follow"],
    )


def test_generic_output_goes_to_declared_port():
    raw = json.dumps({"output": "MOCK_LLM: texto", "_action": "follow"})
    result = _parse_output(raw, _snapshot([{"name": "result", "type": "document"}]))
    assert result == {"result": "MOCK_LLM: texto", "_action": "follow"}


def test_declared_port_kept_when_present():
    raw = json.dumps({"result": "ok", "notes": "x"})
    result = _parse_output(raw, _snapshot([{"name": "result", "type": "document"}]))
    assert result["result"] == "ok" and result["notes"] == "x"
    assert result["_action"] == "follow"


def test_plain_text_goes_to_declared_port():
    result = _parse_output("texto livre", _snapshot([{"name": "spec", "type": "document"}]))
    assert result == {"spec": "texto livre", "_action": "follow"}


def test_without_declared_ports_keeps_output_key():
    result = _parse_output("texto", _snapshot([]))
    assert result == {"output": "texto", "_action": "follow"}
