from __future__ import annotations

from collections import Counter
from typing import Any


def _effect_types(dr: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in dr.get("effect_types", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def validate_effect_semantics(
    effect_value: dict[str, Any],
    target_values: list[dict[str, Any]],
    dr: dict[str, Any],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    effect_type_ref = effect_value.get("effect_type_ref")
    effect_type = _effect_types(dr).get(effect_type_ref)
    if not isinstance(effect_type, dict):
        return [{
            "code": "EFFECT_TYPE_UNREGISTERED",
            "message": f"unknown effect_type_ref: {effect_type_ref!r}",
        }]

    operations = effect_type.get("operation_values")
    if isinstance(operations, list):
        operation = effect_value.get("operation")
        if operation not in operations:
            findings.append({
                "code": "EFFECT_OPERATION_INVALID",
                "message": f"{effect_type_ref} operation must be one of {operations!r}",
            })
            return findings
    else:
        operation = None

    input_refs = effect_value.get("input_refs")
    inputs = input_refs if isinstance(input_refs, list) else []
    minimum_inputs = effect_type.get("min_input_cardinality")
    if isinstance(minimum_inputs, int) and len(inputs) < minimum_inputs:
        findings.append({
            "code": "EFFECT_INPUT_CARDINALITY_UNSATISFIED",
            "message": f"{effect_type_ref} requires at least {minimum_inputs} input_refs",
        })

    exact_inputs = effect_type.get("input_cardinality")
    if isinstance(exact_inputs, int) and len(inputs) != exact_inputs:
        findings.append({
            "code": "EFFECT_INPUT_CARDINALITY_INVALID",
            "message": f"{effect_type_ref} requires exactly {exact_inputs} input_refs",
        })

    target_roles = [
        item.get("target_role")
        for item in target_values
        if isinstance(item, dict) and isinstance(item.get("target_role"), str)
    ]
    counts = Counter(target_roles)

    required_roles = effect_type.get("required_target_roles")
    if isinstance(required_roles, list):
        for role in required_roles:
            if not isinstance(role, str):
                continue
            if counts[role] != 1:
                findings.append({
                    "code": "EFFECT_TARGET_ROLE_CARDINALITY_INVALID",
                    "message": f"{effect_type_ref} requires exactly one target_role={role}",
                })

    by_operation = effect_type.get("operation_target_roles")
    if isinstance(by_operation, dict) and isinstance(operation, str):
        roles = by_operation.get(operation)
        if isinstance(roles, list):
            for role in roles:
                if not isinstance(role, str):
                    continue
                if counts[role] != 1:
                    findings.append({
                        "code": "EFFECT_TARGET_ROLE_CARDINALITY_INVALID",
                        "message": (
                            f"{effect_type_ref} operation={operation} requires exactly "
                            f"one target_role={role}"
                        ),
                    })

    return findings
