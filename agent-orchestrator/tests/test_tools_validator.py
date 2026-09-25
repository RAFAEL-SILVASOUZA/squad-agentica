"""Tests for tools validator: script validation and I/O contract.

Dono: be-skills (FASE 4).
"""

from __future__ import annotations

from app.tools.validator import validate_tool


class TestToolValidator:
    def test_valid_script_and_io(self) -> None:
        script = """
def execute(name: str, count: int = 1) -> dict:
    return {"message": f"Hello {name}"}
"""
        io = {
            "inputs": [
                {"name": "name", "type": "string", "description": "Name", "required": True},
                {"name": "count", "type": "number", "description": "Count", "required": False},
            ],
            "outputs": [
                {"name": "message", "type": "string", "description": "Greeting"},
            ],
        }
        errors = validate_tool(script, io)
        assert errors == []

    def test_empty_script(self) -> None:
        errors = validate_tool("", {"inputs": [], "outputs": []})
        assert any("empty" in e.lower() for e in errors)

    def test_syntax_error(self) -> None:
        script = "def execute(:\n  pass"
        errors = validate_tool(script, {"inputs": [], "outputs": []})
        assert any("syntax error" in e.lower() for e in errors)

    def test_missing_execute_function(self) -> None:
        script = """
def wrong_name() -> dict:
    return {}
"""
        errors = validate_tool(script, {"inputs": [], "outputs": []})
        assert any("execute" in e.lower() for e in errors)

    def test_execute_without_return(self) -> None:
        script = """
def execute(x: int) -> None:
    pass
"""
        errors = validate_tool(script, {"inputs": [], "outputs": []})
        assert any("return" in e.lower() for e in errors)

    def test_execute_without_params(self) -> None:
        script = """
def execute() -> dict:
    return {}
"""
        errors = validate_tool(script, {"inputs": [], "outputs": []})
        assert any("parameter" in e.lower() for e in errors)

    def test_invalid_io_type(self) -> None:
        script = "def execute(x: str) -> dict:\n    return {}\n"
        io = {
            "inputs": [{"name": "x", "type": "invalid_type", "description": ""}],
            "outputs": [],
        }
        errors = validate_tool(script, io)
        assert any("type" in e.lower() for e in errors)

    def test_missing_input_name(self) -> None:
        script = "def execute(x: str) -> dict:\n    return {}\n"
        io = {
            "inputs": [{"type": "string", "description": ""}],
            "outputs": [],
        }
        errors = validate_tool(script, io)
        assert any("name" in e.lower() for e in errors)

    def test_invalid_identifier_name(self) -> None:
        script = "def execute(x: str) -> dict:\n    return {}\n"
        io = {
            "inputs": [{"name": "123-invalid", "type": "string", "description": ""}],
            "outputs": [],
        }
        errors = validate_tool(script, io)
        assert any("identifier" in e.lower() for e in errors)

    def test_duplicate_input_names(self) -> None:
        script = "def execute(x: str) -> dict:\n    return {}\n"
        io = {
            "inputs": [
                {"name": "x", "type": "string", "description": ""},
                {"name": "x", "type": "number", "description": ""},
            ],
            "outputs": [],
        }
        errors = validate_tool(script, io)
        assert any("unique" in e.lower() for e in errors)

    def test_duplicate_output_names(self) -> None:
        script = "def execute(x: str) -> dict:\n    return {}\n"
        io = {
            "inputs": [],
            "outputs": [
                {"name": "result", "type": "string", "description": ""},
                {"name": "result", "type": "number", "description": ""},
            ],
        }
        errors = validate_tool(script, io)
        assert any("unique" in e.lower() for e in errors)

    def test_valid_types_accepted(self) -> None:
        script = "def execute(x: str) -> dict:\n    return {}\n"
        for valid_type in ["string", "number", "boolean", "object", "array"]:
            io = {
                "inputs": [{"name": "x", "type": valid_type, "description": ""}],
                "outputs": [],
            }
            errors = validate_tool(script, io)
            assert not any("type" in e.lower() for e in errors), f"Failed for type {valid_type}"

    def test_non_dict_param(self) -> None:
        script = "def execute(x: str) -> dict:\n    return {}\n"
        io = {
            "inputs": ["not_a_dict"],
            "outputs": [],
        }
        errors = validate_tool(script, io)
        assert any("object" in e.lower() for e in errors)
