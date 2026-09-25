"""Tests for tools sandbox: timeout, isolation, malicious script.

Dono: be-skills (FASE 4).
"""

from __future__ import annotations

from app.tools.sandbox import ToolSandbox


class TestToolSandbox:
    async def test_simple_execution(self) -> None:
        """Tool simples retorna resultado correto."""
        sandbox = ToolSandbox(timeout=10)
        script = """
def execute(x: int, y: int) -> dict:
    return {"sum": x + y}
"""
        result = await sandbox.execute(script, {"x": 3, "y": 4})
        assert result == {"sum": 7}

    async def test_execution_with_error(self) -> None:
        """Tool que lanca excecao retorna error."""
        sandbox = ToolSandbox(timeout=10)
        script = """
def execute() -> dict:
    raise ValueError("something went wrong")
"""
        result = await sandbox.execute(script, {})
        assert "error" in result
        assert "something went wrong" in result["error"]

    async def test_timeout(self) -> None:
        """Tool que excede o timeout retorna erro de timeout."""
        sandbox = ToolSandbox(timeout=2)
        script = """
import time
def execute() -> dict:
    time.sleep(10)
    return {"done": True}
"""
        result = await sandbox.execute(script, {}, timeout=2)
        assert "error" in result
        assert "timed out" in result["error"]

    async def test_no_access_to_host_env(self) -> None:
        """Sandbox nao tem acesso a variaveis de ambiente do host."""
        sandbox = ToolSandbox(timeout=10)
        script = """
import os
def execute() -> dict:
    return {"has_secret": "MY_SECRET" in os.environ}
"""
        result = await sandbox.execute(script, {})
        assert result.get("has_secret") is False

    async def test_malicious_script_captured(self) -> None:
        """Script malicioso (tentativa de acesso a filesystem) e capturado."""
        sandbox = ToolSandbox(timeout=10)
        script = """
import os
def execute() -> dict:
    # Tenta ler /etc/passwd (deve falhar ou nao ter acesso).
    try:
        with open("/etc/passwd") as f:
            return {"content": f.read()}
    except Exception as e:
        return {"error": str(e)}
"""
        result = await sandbox.execute(script, {})
        # O script pode ou nao ter acesso (depende do container),
        # mas o resultado deve ser capturado sem crashar o sandbox.
        assert isinstance(result, dict)

    async def test_max_timeout_capped(self) -> None:
        """Timeout acima do maximo e limitado a 120s."""
        sandbox = ToolSandbox(timeout=999)
        # O timeout interno deve ser 120.
        assert sandbox._timeout == 120

    async def test_empty_script(self) -> None:
        """Script vazio retorna erro."""
        sandbox = ToolSandbox(timeout=10)
        result = await sandbox.execute("", {})
        assert "error" in result

    async def test_no_execute_function(self) -> None:
        """Script sem funcao execute retorna erro."""
        sandbox = ToolSandbox(timeout=10)
        script = """
def wrong_function() -> dict:
    return {"ok": True}
"""
        result = await sandbox.execute(script, {})
        assert "error" in result

    async def test_json_serializable_result(self) -> None:
        """Resultado deve ser JSON-serializavel."""
        sandbox = ToolSandbox(timeout=10)
        script = """
def execute() -> dict:
    return {"items": [1, 2, 3], "name": "test", "flag": True}
"""
        result = await sandbox.execute(script, {})
        assert result == {"items": [1, 2, 3], "name": "test", "flag": True}

    async def test_env_injection(self) -> None:
        """Variaveis de ambiente injetadas estao disponiveis no sandbox."""
        sandbox = ToolSandbox(timeout=10)
        script = """
import os
def execute() -> dict:
    return {"token": os.environ.get("TEST_TOKEN", "missing")}
"""
        result = await sandbox.execute(script, {}, env={"TEST_TOKEN": "abc123"})
        assert result == {"token": "abc123"}
