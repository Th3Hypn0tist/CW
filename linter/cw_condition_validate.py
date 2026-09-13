from __future__ import annotations

from typing import Any


def _expected_value_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    return None


def validate_event_condition_value(
    value: dict[str, Any],
    ruleset: dict[str, Any],
) -> list[dict[str, str]]:
    """Validate one event_condition Link value against its DR ruleset.

    This validator is intentionally structural. Runtime satisfaction of the
    condition depends on execution-context Data state and is defined by DR.
    """
    findings: list[dict[str, str]] = []
    mode = value.get("condition_mode")
    supported = ruleset.get("supported_condition_modes")
    supported_modes = {
        item for item in supported if isinstance(item, str)
    } if isinstance(supported, list) else set()

    if not isinstance(mode, str) or mode not in supported_modes:
        findings.append({
            "code": "EVENT_CONDITION_MODE_INVALID",
            "message": f"unsupported condition_mode: {mode!r}",
        })
        return findings

    mode_fields = ruleset.get("mode_fields")
    mode_contract = mode_fields.get(mode) if isinstance(mode_fields, dict) else None
    if isinstance(mode_contract, dict):
        required = mode_contract.get("required")
        for field in required if isinstance(required, list) else []:
            if isinstance(field, str) and field not in value:
                findings.append({
                    "code": "EVENT_CONDITION_FIELD_REQUIRED",
                    "message": f"condition_mode={mode} requires {field}",
                })
        forbidden = mode_contract.get("forbidden")
        for field in forbidden if isinstance(forbidden, list) else []:
            if isinstance(field, str) and field in value:
                findings.append({
                    "code": "EVENT_CONDITION_FIELD_FORBIDDEN",
                    "message": f"condition_mode={mode} forbids {field}",
                })

    if mode == "value_equals" and "expected_value" in value:
        observed_type = _expected_value_type(value.get("expected_value"))
        allowed = ruleset.get("expected_value_types")
        allowed_types = {
            item for item in allowed if isinstance(item, str)
        } if isinstance(allowed, list) else set()
        if observed_type is None or observed_type not in allowed_types:
            findings.append({
                "code": "EVENT_CONDITION_EXPECTED_VALUE_TYPE_INVALID",
                "message": (
                    "expected_value must be one of the explicitly supported "
                    f"scalar types: {sorted(allowed_types)}"
                ),
            })

    return findings
