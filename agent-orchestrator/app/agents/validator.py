"""Agent contract validator: validates ports (inputs/outputs) and actions.

Dono: be-agents (FASE 4). Regras (spec 4.1 + D4 4.2):
- `inputs`/`outputs`: lista de PortDef com `name` único, `type` na whitelist,
  `required` booleano.
- `actions`: lista de FlowAction, cada um ∈ {follow, return, finalize}.
- Erros retornados como lista de dicts para o envelope 400.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Whitelist de tipos de port (spec 4.1: "document" | "code" | "artifact" | "signal").
VALID_PORT_TYPES: frozenset[str] = frozenset({"document", "code", "artifact", "signal"})

# Whitelist de actions (spec 4.1: "follow" | "return" | "finalize").
VALID_ACTIONS: frozenset[str] = frozenset({"follow", "return", "finalize"})


@dataclass
class ValidationError:
    """Um erro de validação de contrato."""

    rule: str
    message: str
    nodeId: str | None = None
    edgeId: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        d: dict[str, str | None] = {"rule": self.rule, "message": self.message}
        if self.nodeId:
            d["nodeId"] = self.nodeId
        if self.edgeId:
            d["edgeId"] = self.edgeId
        return d


@dataclass
class ValidationResult:
    """Resultado da validação de contrato do agente."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)


def validate_agent_contract(
    inputs: list[dict],
    outputs: list[dict],
    actions: list[str],
) -> ValidationResult:
    """Valida o contrato de entrada/saída/actions de um agente.

    Regras:
    1. Cada port (input/output) deve ter `name` (string não-vazia).
    2. Nomes de ports devem ser únicos DENTRO de inputs e DENTRO de outputs
       (inputs e outputs podem ter nomes iguais, são domínios distintos).
    3. `type` de cada port deve estar na whitelist.
    4. `required` de cada port deve ser booleano.
    5. Cada action deve estar na whitelist.
    6. Actions não podem ter duplicatas.
    """
    errors: list[ValidationError] = []

    # Validate inputs.
    _validate_ports(inputs, "inputs", errors)

    # Validate outputs.
    _validate_ports(outputs, "outputs", errors)

    # Validate actions.
    seen_actions: set[str] = set()
    for i, action in enumerate(actions):
        if not isinstance(action, str):
            errors.append(
                ValidationError(
                    rule="action_type",
                    message=f"actions[{i}] must be a string, got {type(action).__name__}",
                )
            )
            continue
        if action not in VALID_ACTIONS:
            allowed = sorted(VALID_ACTIONS)
            errors.append(
                ValidationError(
                    rule="action_whitelist",
                    message=f"actions[{i}] '{action}' is not in the allowed set: {allowed}",
                )
            )
        if action in seen_actions:
            errors.append(
                ValidationError(
                    rule="action_duplicate",
                    message=f"actions[{i}] '{action}' is duplicated",
                )
            )
        seen_actions.add(action)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def _validate_ports(ports: list[dict], direction: str, errors: list[ValidationError]) -> None:
    """Valida uma lista de PortDef (inputs ou outputs)."""
    seen_names: set[str] = set()

    for i, port in enumerate(ports):
        prefix = f"{direction}[{i}]"

        # Must be a dict.
        if not isinstance(port, dict):
            errors.append(
                ValidationError(
                    rule="port_type",
                    message=f"{prefix} must be an object, got {type(port).__name__}",
                )
            )
            continue

        # name: required, non-empty string.
        name = port.get("name")
        if not name or not isinstance(name, str):
            errors.append(
                ValidationError(
                    rule="port_name_required",
                    message=f"{prefix}.name is required and must be a non-empty string",
                )
            )
        else:
            if name in seen_names:
                errors.append(
                    ValidationError(
                        rule="port_name_unique",
                        message=f"{prefix}.name '{name}' is duplicated within {direction}",
                    )
                )
            seen_names.add(name)

        # type: required, must be in whitelist.
        port_type = port.get("type")
        if not port_type or not isinstance(port_type, str):
            errors.append(
                ValidationError(
                    rule="port_type_required",
                    message=f"{prefix}.type is required and must be a string",
                )
            )
        elif port_type not in VALID_PORT_TYPES:
            errors.append(
                ValidationError(
                    rule="port_type_whitelist",
                    message=(
                        f"{prefix}.type '{port_type}' is not in the allowed set: "
                        f"{sorted(VALID_PORT_TYPES)}"
                    ),
                )
            )

        # required: must be boolean.
        required = port.get("required")
        if not isinstance(required, bool):
            errors.append(
                ValidationError(
                    rule="port_required_type",
                    message=f"{prefix}.required must be a boolean, got {type(required).__name__}",
                )
            )


def errors_to_details(result: ValidationResult) -> dict:
    """Converte ValidationResult para o formato do envelope 400."""
    return {"errors": [e.to_dict() for e in result.errors]}
