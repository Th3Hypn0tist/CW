from __future__ import annotations

from typing import Any, Iterable


class SemanticGapError(ValueError):
    pass


def _functions(symbols: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for symbol in symbols:
        if not isinstance(symbol, dict):
            continue
        kind = symbol.get("kind")
        if kind in {"function", "method"}:
            yield symbol
            yield from _functions(symbol.get("nested_functions", []))
        elif kind == "class":
            yield from _functions(symbol.get("methods", []))


def _call_targets(function: dict[str, Any]) -> tuple[str, ...]:
    logic = function.get("logic") if isinstance(function.get("logic"), dict) else {}
    calls = logic.get("calls") if isinstance(logic.get("calls"), list) else []
    return tuple(
        item["target"]
        for item in calls
        if isinstance(item, dict) and isinstance(item.get("target"), str) and item.get("target")
    )


def _literal_bindings(language_ir: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for symbol in language_ir.get("symbols", []) if isinstance(language_ir.get("symbols"), list) else []:
        if not isinstance(symbol, dict) or symbol.get("kind") != "variable":
            continue
        names = symbol.get("names") if isinstance(symbol.get("names"), list) else []
        if len(names) != 1 or not isinstance(names[0], str) or "literal_value" not in symbol:
            continue
        out[names[0]] = symbol.get("literal_value")
    return out


def _matches_target(target: str, wanted: str) -> bool:
    return target == wanted or target.endswith("." + wanted)


def _base_gap(rule: dict[str, Any], file_record: dict[str, Any], function: dict[str, Any] | None) -> dict[str, Any]:
    source_path = file_record.get("path")
    owner = file_record.get("canonical_file_ref")
    function_name = function.get("qualified_name") if isinstance(function, dict) else None
    source_location = source_path if not function_name else f"{source_path}::{function_name}"
    return {
        "id": rule["id"],
        "classification": rule["classification"],
        "source_entity_ref": owner,
        "source_location": source_location,
        "observed_semantics": rule["observed_semantics"],
        "missing_cw_semantics": rule.get("missing_cw_semantics"),
        "why_existing_constructs_are_insufficient": rule.get("why_existing_constructs_are_insufficient"),
        "candidate_extension": rule.get("candidate_extension"),
        "ccf_change_required": bool(rule.get("ccf_change_required", False)),
        "blocking": bool(rule.get("blocking", False)),
        "canonical_semantic_authority": False,
    }


def detect_semantic_gaps(ir: dict[str, Any], rules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(ir, dict):
        raise SemanticGapError("Code IR must be an object")
    normalized = [dict(rule) for rule in rules if isinstance(rule, dict)]
    ids = [rule.get("id") for rule in normalized]
    if any(not isinstance(value, str) or not value for value in ids):
        raise SemanticGapError("semantic gap rule id must be non-empty string")
    if len(ids) != len(set(ids)):
        raise SemanticGapError("duplicate semantic gap rule id")

    files = [item for item in ir.get("files", []) if isinstance(item, dict)]
    findings: list[dict[str, Any]] = []

    for rule in normalized:
        path = rule.get("source_path")
        if not isinstance(path, str) or not path:
            raise SemanticGapError(f"semantic gap rule {rule['id']} source_path missing")
        hits = [item for item in files if item.get("path") == path]
        if not hits:
            continue
        file_record = hits[0]
        language_ir = file_record.get("language_ir") if isinstance(file_record.get("language_ir"), dict) else {}
        evidence_kind = rule.get("evidence_kind")

        if evidence_kind == "call_target":
            wanted = rule.get("targets") if isinstance(rule.get("targets"), list) else []
            function_filter = set(rule.get("functions", [])) if isinstance(rule.get("functions"), list) else set()
            for function in _functions(language_ir.get("symbols", [])):
                qualified = function.get("qualified_name")
                if function_filter and qualified not in function_filter and function.get("name") not in function_filter:
                    continue
                matched = sorted({
                    target
                    for target in _call_targets(function)
                    for item in wanted
                    if isinstance(item, str) and _matches_target(target, item)
                })
                if not matched:
                    continue
                finding = _base_gap(rule, file_record, function)
                finding["evidence"] = {"kind": "call_target", "targets": matched}
                findings.append(finding)

        elif evidence_kind == "literal_binding":
            binding = rule.get("binding")
            expected = rule.get("value")
            literals = _literal_bindings(language_ir)
            if isinstance(binding, str) and binding in literals and literals[binding] == expected:
                finding = _base_gap(rule, file_record, None)
                finding["evidence"] = {
                    "kind": "literal_binding",
                    "binding": binding,
                    "value": literals[binding],
                }
                findings.append(finding)
        else:
            raise SemanticGapError(f"unsupported semantic gap evidence_kind: {evidence_kind!r}")

    findings.sort(key=lambda item: (str(item.get("id")), str(item.get("source_location"))))
    return findings


def gap_report(ir: dict[str, Any], rules: Iterable[dict[str, Any]]) -> dict[str, Any]:
    gaps = detect_semantic_gaps(ir, rules)
    return {
        "kind": "cic_semantic_gap_report",
        "version": "1.0.0",
        "canonical_semantic_authority": False,
        "summary": {
            "total": len(gaps),
            "cw_semantic_gaps": sum(item.get("classification") == "cw_semantic_gap" for item in gaps),
            "cic_mapping_gaps": sum(item.get("classification") == "cic_mapping_gap" for item in gaps),
            "blocking": sum(bool(item.get("blocking")) for item in gaps),
        },
        "gaps": gaps,
    }
