"""Tests for agent contract validator (D4 4.2).

Cobre todas as regras de port/action:
- name único, type whitelist, required booleano
- actions whitelist, sem duplicatas
"""

from __future__ import annotations

from app.agents.validator import (
    VALID_ACTIONS,
    VALID_PORT_TYPES,
    validate_agent_contract,
)


class TestPortValidation:
    def test_valid_ports(self):
        inputs = [{"name": "req", "type": "document", "required": True}]
        outputs = [{"name": "plan", "type": "document", "required": False}]
        result = validate_agent_contract(inputs, outputs, ["follow"])
        assert result.valid
        assert result.errors == []

    def test_port_missing_name(self):
        inputs = [{"type": "document", "required": True}]
        result = validate_agent_contract(inputs, [], [])
        assert not result.valid
        assert any(e.rule == "port_name_required" for e in result.errors)

    def test_port_empty_name(self):
        inputs = [{"name": "", "type": "document", "required": True}]
        result = validate_agent_contract(inputs, [], [])
        assert not result.valid
        assert any(e.rule == "port_name_required" for e in result.errors)

    def test_port_duplicate_name_in_inputs(self):
        inputs = [
            {"name": "data", "type": "document", "required": True},
            {"name": "data", "type": "code", "required": False},
        ]
        result = validate_agent_contract(inputs, [], [])
        assert not result.valid
        assert any(e.rule == "port_name_unique" for e in result.errors)

    def test_port_duplicate_name_in_outputs(self):
        outputs = [
            {"name": "result", "type": "code", "required": True},
            {"name": "result", "type": "document", "required": False},
        ]
        result = validate_agent_contract([], outputs, [])
        assert not result.valid
        assert any(e.rule == "port_name_unique" for e in result.errors)

    def test_same_name_in_inputs_and_outputs_is_ok(self):
        inputs = [{"name": "data", "type": "document", "required": True}]
        outputs = [{"name": "data", "type": "code", "required": False}]
        result = validate_agent_contract(inputs, outputs, [])
        assert result.valid

    def test_port_invalid_type(self):
        inputs = [{"name": "x", "type": "invalid_type", "required": True}]
        result = validate_agent_contract(inputs, [], [])
        assert not result.valid
        assert any(e.rule == "port_type_whitelist" for e in result.errors)

    def test_port_missing_type(self):
        inputs = [{"name": "x", "required": True}]
        result = validate_agent_contract(inputs, [], [])
        assert not result.valid
        assert any(e.rule == "port_type_required" for e in result.errors)

    def test_port_required_not_boolean(self):
        inputs = [{"name": "x", "type": "document", "required": "yes"}]
        result = validate_agent_contract(inputs, [], [])
        assert not result.valid
        assert any(e.rule == "port_required_type" for e in result.errors)

    def test_port_not_a_dict(self):
        inputs = ["not_a_dict"]
        result = validate_agent_contract(inputs, [], [])
        assert not result.valid
        assert any(e.rule == "port_type" for e in result.errors)

    def test_all_valid_port_types_accepted(self):
        for port_type in VALID_PORT_TYPES:
            inputs = [{"name": "x", "type": port_type, "required": True}]
            result = validate_agent_contract(inputs, [], [])
            assert result.valid, f"Port type '{port_type}' should be valid"


class TestActionValidation:
    def test_valid_actions(self):
        result = validate_agent_contract([], [], ["follow", "return", "finalize"])
        assert result.valid

    def test_invalid_action(self):
        result = validate_agent_contract([], [], ["invalid_action"])
        assert not result.valid
        assert any(e.rule == "action_whitelist" for e in result.errors)

    def test_duplicate_action(self):
        result = validate_agent_contract([], [], ["follow", "follow"])
        assert not result.valid
        assert any(e.rule == "action_duplicate" for e in result.errors)

    def test_empty_actions_is_valid(self):
        result = validate_agent_contract([], [], [])
        assert result.valid

    def test_action_not_a_string(self):
        result = validate_agent_contract([], [], [123])
        assert not result.valid
        assert any(e.rule == "action_type" for e in result.errors)

    def test_all_valid_actions_accepted(self):
        for action in VALID_ACTIONS:
            result = validate_agent_contract([], [], [action])
            assert result.valid, f"Action '{action}' should be valid"


class TestCombinedValidation:
    def test_multiple_errors_reported(self):
        inputs = [
            {"name": "", "type": "bad", "required": "no"},
            {"name": "dup", "type": "document", "required": True},
            {"name": "dup", "type": "code", "required": False},
        ]
        actions = ["follow", "follow", "bad_action"]
        result = validate_agent_contract(inputs, [], actions)
        assert not result.valid
        # Should have multiple errors.
        assert len(result.errors) >= 4

    def test_empty_everything_is_valid(self):
        result = validate_agent_contract([], [], [])
        assert result.valid
