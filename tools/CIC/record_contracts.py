from __future__ import annotations

import ast
from typing import Any, Iterable


class RecordContractError(ValueError):
    pass


def _functions(symbols: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for symbol in symbols:
        if not isinstance(symbol, dict):
            continue
        if symbol.get("kind") in {"function", "method"}:
            yield symbol
            yield from _functions(symbol.get("nested_functions", []))
        elif symbol.get("kind") == "class":
            yield from _functions(symbol.get("methods", []))


def _infer_value_type(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in {"str", "int", "bool", "float"}:
            return {
                "str": "string",
                "int": "integer",
                "bool": "boolean",
                "float": "number",
            }[node.func.id]
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "boolean"
        if isinstance(node.value, str):
            return "string"
        if isinstance(node.value, int):
            return "integer"
        if isinstance(node.value, float):
            return "number"
    if isinstance(node, ast.IfExp):
        left = _infer_value_type(node.body)
        right = _infer_value_type(node.orelse)
        return left if left == right else None
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Dict):
        return "record"
    return None


def _serialized_fields(method: dict[str, Any]) -> list[dict[str, Any]]:
    source = method.get("source")
    if not isinstance(source, str) or not source.strip():
        return []
    try:
        tree = ast.parse(source, type_comments=True)
    except SyntaxError:
        return []
    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    best: list[dict[str, Any]] = []
    for node in ast.walk(tree.body[0]):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        fields: list[dict[str, Any]] = []
        valid = True
        for key, value in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                valid = False
                break
            fields.append({
                "name": key.value,
                "observed_type": _infer_value_type(value),
            })
        if valid and len(fields) > len(best):
            best = fields
    return best


def detect_record_contract_candidates(ir: dict[str, Any], rules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(ir, dict):
        raise RecordContractError("Code IR must be an object")
    files = [item for item in ir.get("files", []) if isinstance(item, dict)]
    result: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("rule_id")
        source_path = rule.get("source_path")
        class_name = rule.get("class_name")
        serializer = rule.get("serializer_method", "to_dict")
        namespace = rule.get("contract_namespace")
        if not all(isinstance(value, str) and value for value in (rule_id, source_path, class_name, serializer)):
            raise RecordContractError("invalid record contract rule")
        if namespace is not None and (not isinstance(namespace, str) or not namespace.strip()):
            raise RecordContractError(f"invalid contract namespace for {rule_id}")
        file_record = next((item for item in files if item.get("path") == source_path), None)
        if not isinstance(file_record, dict):
            continue
        language_ir = file_record.get("language_ir") if isinstance(file_record.get("language_ir"), dict) else {}
        class_record = next(
            (
                symbol for symbol in language_ir.get("symbols", [])
                if isinstance(symbol, dict)
                and symbol.get("kind") == "class"
                and symbol.get("name") == class_name
            ),
            None,
        )
        if not isinstance(class_record, dict):
            continue
        method = next(
            (
                item for item in class_record.get("methods", [])
                if isinstance(item, dict) and item.get("name") == serializer
            ),
            None,
        )
        if not isinstance(method, dict):
            continue
        fields = _serialized_fields(method)
        if not fields:
            continue
        result.append({
            "candidate_id": f"RECORD_CONTRACT::{rule_id}::{file_record.get('canonical_file_ref')}::{class_name}",
            "rule_ref": rule_id,
            "contract_namespace": namespace,
            "source_entity_ref": file_record.get("canonical_file_ref"),
            "source_path": source_path,
            "source_class": class_name,
            "serializer_method": serializer,
            "serialized_fields": fields,
            "canonical_ready": False,
            "canonical_semantic_authority": False,
            "authority": "implementation_evidence",
        })
    return sorted(result, key=lambda item: item["candidate_id"])
