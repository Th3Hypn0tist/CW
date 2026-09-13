from __future__ import annotations

from typing import Any


def audit_schema_capabilities(ir: dict[str, Any], dr: dict[str, Any]) -> dict[str, Any]:
    semantics = dr.get("schema_semantics") if isinstance(dr.get("schema_semantics"), dict) else {}
    supported = set(semantics)
    findings: list[dict[str, Any]] = []

    candidates = ir.get("record_contract_candidates") if isinstance(ir.get("record_contract_candidates"), list) else []
    for candidate in candidates:
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

    findings.sort(key=lambda item: (
        str(item.get("source_entity_ref")),
        str(item.get("source_contract")),
        str(item.get("field")),
    ))
    return {
        "kind": "cic_schema_capability_report",
        "version": "1.0.0",
        "canonical_semantic_authority": False,
        "format_dr_version": dr.get("version"),
        "supported_schema_semantics": sorted(supported),
        "summary": {
            "record_contracts": len([item for item in candidates if isinstance(item, dict)]),
            "unsupported_fields": len(findings),
            "unsupported_types": sorted({item["observed_type"] for item in findings}),
        },
        "findings": findings,
    }
