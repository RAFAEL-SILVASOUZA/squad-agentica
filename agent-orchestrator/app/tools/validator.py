"""Tools custom validator: valida script Python e contrato de I/O.

Dono: be-skills (FASE 4). Spec 6.4:
- Script deve compilar (syntactically valid Python).
- Script deve ter uma funcao `execute` com assinatura coerente.
- Contrato de I/O: inputs/outputs coerentes (nome, tipo, descricao).
"""

from __future__ import annotations

import ast
import re
from typing import Any

VALID_TYPES = {"string", "number", "boolean", "object", "array"}


def validate_tool(script: str, io: dict[str, Any]) -> list[str]:
    """Valida o script e o contrato de I/O de uma tool custom.

    Retorna uma lista de erros (vazia se valido).
    """
    errors: list[str] = []

    # 1. Valida o script Python.
    script_errors = _validate_script(script)
    errors.extend(script_errors)

    # 2. Valida o contrato de I/O.
    io_errors = _validate_io(io)
    errors.extend(io_errors)

    return errors


def _validate_script(script: str) -> list[str]:
    """Valida que o script e Python valido e tem a funcao execute."""
    errors: list[str] = []

    if not script or not script.strip():
        return ["Script is empty"]

    # Tenta compilar.
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return [f"Script has syntax error at line {e.lineno}: {e.msg}"]

    # Verifica se existe uma funcao `execute`.
    has_execute = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "execute":
            has_execute = True
            # O sandbox chama ``execute(**args)``: aceita parâmetros nomeados,
            # keyword-only, ``*args`` ou ``**kwargs`` (o placeholder da UI é
            # ``def execute(**kwargs)``, antes rejeitado no deploy).
            a = node.args
            if not (a.args or a.kwonlyargs or a.vararg or a.kwarg):
                errors.append("Function 'execute' must have at least one parameter")
            break

    if not has_execute:
        errors.append("Script must define a function named 'execute'")

    # Verifica se a funcao execute tem um return.
    if has_execute:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "execute":
                has_return = any(
                    isinstance(n, ast.Return) and n.value is not None
                    for n in ast.walk(node)
                )
                if not has_return:
                    errors.append("Function 'execute' must return a value")
                break

    return errors


def _validate_io(io: dict[str, Any]) -> list[str]:
    """Valida o contrato de I/O (inputs e outputs)."""
    errors: list[str] = []

    inputs = io.get("inputs", [])
    outputs = io.get("outputs", [])

    if not isinstance(inputs, list):
        errors.append("'inputs' must be a list")
    if not isinstance(outputs, list):
        errors.append("'outputs' must be a list")
        return errors

    # Valida cada input.
    for i, param in enumerate(inputs):
        errors.extend(_validate_param(param, f"inputs[{i}]"))

    # Valida cada output.
    for i, param in enumerate(outputs):
        errors.extend(_validate_param(param, f"outputs[{i}]"))

    # Verifica nomes unicos.
    input_names = [p.get("name", "") for p in inputs if isinstance(p, dict)]
    if len(input_names) != len(set(input_names)):
        errors.append("Input parameter names must be unique")

    output_names = [p.get("name", "") for p in outputs if isinstance(p, dict)]
    if len(output_names) != len(set(output_names)):
        errors.append("Output parameter names must be unique")

    return errors


def _validate_param(param: Any, context: str) -> list[str]:
    """Valida um parametro individual do contrato de I/O."""
    errors: list[str] = []

    if not isinstance(param, dict):
        return [f"{context} must be an object"]

    name = param.get("name")
    if not name or not isinstance(name, str):
        errors.append(f"{context}.name is required and must be a string")
    elif not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        errors.append(f"{context}.name must be a valid identifier: {name}")

    ptype = param.get("type")
    if not ptype:
        errors.append(f"{context}.type is required")
    elif ptype not in VALID_TYPES:
        errors.append(f"{context}.type must be one of {VALID_TYPES}, got: {ptype}")

    description = param.get("description")
    if description is not None and not isinstance(description, str):
        errors.append(f"{context}.description must be a string")

    required = param.get("required")
    if required is not None and not isinstance(required, bool):
        errors.append(f"{context}.required must be a boolean")

    return errors
