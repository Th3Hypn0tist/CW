from __future__ import annotations

from typing import Any, Iterable


class StateContractError(ValueError):
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


def _literal_bindings(language_ir: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for symbol in language_ir.get("symbols", []):
        if not isinstance(symbol, dict) or symbol.get("kind") != "variable":
            continue
        names = symbol.get("names") if isinstance(symbol.get("names"), list) else []
        if len(names) == 1 and isinstance(names[0], str) and "literal_value" in symbol:
            out[names[0]] = symbol.get("literal_value")
    return out


def _call_targets(function: dict[str, Any]) -> set[str]:
    logic = function.get("logic") if isinstance(function.get("logic"), dict) else {}
    calls = logic.get("calls") if isinstance(logic.get("calls"), list) else []
    return {
        item["target"]
        for item in calls
        if isinstance(item, dict) and isinstance(item.get("target"), str) and item.get("target")
    }


def _matches(targets: set[str], wanted: Iterable[str]) -> bool:
    for target in targets:
        for name in wanted:
            if isinstance(name, str) and (target == name or target.endswith("." + name)):
                return True
    return False


def detect_state_contract_candidates(ir: dict[str, Any], rules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(ir, dict):
        raise StateContractError("Code IR must be an object")
    files = [item for item in ir.get("files", []) if isinstance(item, dict)]
    result: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("rule_id")
        source_path = rule.get("source_path")
        binding = rule.get("symbol_binding")
        if not all(isinstance(value, str) and value for value in (rule_id, source_path, binding)):
            raise StateContractError("invalid state contract rule")
        file_record = next((item for item in files if item.get("path") == source_path), None)
        if not isinstance(file_record, dict):
            continue
        language_ir = file_record.get("language_ir") if isinstance(file_record.get("language_ir"), dict) else {}
        state_symbol = _literal_bindings(language_ir).get(binding)
        if not isinstance(state_symbol, str) or not state_symbol:
            continue
        readers: list[str] = []
        writers: list[str] = []
        for function in _functions(language_ir.get("symbols", [])):
            qualified = function.get("qualified_name")
            if not isinstance(qualified, str) or not qualified:
                continue
            source = function.get("source")
            if not isinstance(source, str) or binding not in source:
                continue
            calls = _call_targets(function)
            if _matches(calls, rule.get("read_targets", [])):
                readers.append(qualified)
            if _matches(calls, rule.get("write_targets", [])):
                writers.append(qualified)
        result.append({
            "candidate_id": f"STATE_CONTRACT::{rule_id}::{file_record.get('canonical_file_ref')}",
            "rule_ref": rule_id,
            "source_entity_ref": file_record.get("canonical_file_ref"),
            "source_path": source_path,
            "symbol_binding": binding,
            "state_symbol": state_symbol,
            "readers": sorted(set(readers)),
            "writers": sorted(set(writers)),
            "shape_fields": list(rule.get("shape_fields", [])),
            "canonical_ready": False,
            "canonical_semantic_authority": False,
            "authority": "implementation_evidence",
        })
    return sorted(result, key=lambda item: item["candidate_id"])
