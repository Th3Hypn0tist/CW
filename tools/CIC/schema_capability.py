from __future__ import annotations

from typing import Any


def audit_schema_capabilities(ir: dict[str, Any], dr: dict[str, Any]) -> dict[str, Any]:
    semantics = dr.get("schema_semantics") if isinstance(dr.get("schema_semantics"), dict) else {}
    schema_types = dr.get("schema_types")
    supported = {
        item for item in schema_types
        if isinstance(item, str) and item
    } if isinstance(schema_types, list) else set(semantics)
    findings: list[dict[str, Any]] = []

    record_candidates = ir.get("record_contract_candidates") if isinstance(ir.get("record_contract_candidates"), list) else []
    for candidate in record_candidates:
        if not isinstance(candidate, dict):
            continue
        for field in candidate.get("serialized_fields", []) if isinstance(candidate.get("serialized_fields"), list) else []:
            if not isinstance(field, dict):
                continue
            observed = field.get("observed_type")
            if not isinstance(observed, str) or not observed or observed in supported:
                continue
            findings.append({
                "code": "SCHEMA_SEMANTIC_UNSUPPORTED",
                "source_entity_ref": candidate.get("source_entity_ref"),
                "source_contract": candidate.get("source_class"),
                "field": field.get("name"),
                "observed_type": observed,
                "supported_schema_semantics": sorted(supported),
                "ccf_change_required": False,
                "canonical_semantic_authority": False,
            })

    state_candidates = ir.get("state_contract_candidates") if isinstance(ir.get("state_contract_candidates"), list) else []
    for candidate in state_candidates:
        if not isinstance(candidate, dict):
            continue
        observed_types = candidate.get("observed_container_types")
        if not isinstance(observed_types, list):
            continue
        for observed in observed_types:
            if not isinstance(observed, str) or not observed or observed in supported:
                continue
            findings.append({
                "code": "SCHEMA_CONTAINER_UNSUPPORTED",
                "source_entity_ref": candidate.get("source_entity_ref"),
                "source_contract": candidate.get("state_symbol"),
                "field": "$container",
                "observed_type": observed,
                "supported_schema_semantics": sorted(supported),
                "ccf_change_required": False,
                "canonical_semantic_authority": False,
            })

    findings.sort(key=lambda item: (
        str(item.get("source_entity_ref")),
        str(item.get("source_contract")),
        str(item.get("field")),
    ))
    return {
        "kind": "cic_schema_capability_report",
        "version": "1.1.0",
        "canonical_semantic_authority": False,
        "format_dr_version": dr.get("version"),
        "supported_schema_semantics": sorted(supported),
        "summary": {
            "record_contracts": len([item for item in record_candidates if isinstance(item, dict)]),
            "state_contracts": len([item for item in state_candidates if isinstance(item, dict)]),
            "unsupported_fields": len(findings),
            "unsupported_types": sorted({item["observed_type"] for item in findings}),
        },
        "findings": findings,
    }
