from __future__ import annotations

from typing import Any, Iterable


class ContractMaterializationError(ValueError):
    pass


def _fragment(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_").upper()


def _entity_fragment(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value).strip("_")


def materialize_record_contracts(
    candidates: Iterable[dict[str, Any]],
    *,
    namespace: str,
    supported_schema_types: set[str],
) -> list[dict[str, Any]]:
    """Project fully observed serialized records into canonical CTRCT/schema Entities.

    Only fields with an observed schema type supported by the package-local DR are
    eligible. Partial or unsupported records remain diagnostics and are not
    materialized as canonical contracts.
    """
    if not isinstance(namespace, str) or not namespace.strip():
        raise ContractMaterializationError("contract namespace must be non-empty")
    ns = _entity_fragment(namespace.strip())
    result: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    seen_properties: set[str] = set()

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_class = candidate.get("source_class")
        source_entity = candidate.get("source_entity_ref")
        fields = candidate.get("serialized_fields")
        if not isinstance(source_class, str) or not source_class or not isinstance(source_entity, str) or not source_entity:
            continue
        if not isinstance(fields, list) or not fields:
            continue

        definition_fields: dict[str, dict[str, Any]] = {}
        complete = True
        for field in fields:
            if not isinstance(field, dict):
                complete = False
                break
            name = field.get("name")
            observed = field.get("observed_type")
            if not isinstance(name, str) or not name or not isinstance(observed, str) or observed not in supported_schema_types:
                complete = False
                break
            definition_fields[name] = {"type": observed, "required": True}
        if not complete:
            continue

        class_fragment = _entity_fragment(source_class)
        entity_id = f"#CTRCT:{ns}:{class_fragment}"
        schema_id = f"SCHEMA_{_fragment(ns)}_{_fragment(source_class)}"
        if entity_id in seen_entities or schema_id in seen_properties:
            raise ContractMaterializationError(f"duplicate materialized contract identity: {entity_id} / {schema_id}")
        seen_entities.add(entity_id)
        seen_properties.add(schema_id)

        result.append({
            "id": entity_id,
            "name": f"{namespace} {source_class} Contract",
            "entity_type_ref": "CTRCT/schema",
            "status": "unlocked",
            "properties": [
                {
                    "id": f"MEMBERS::{entity_id}",
                    "property_type_ref": "members",
                    "ruleset_ref": "RULESET_MEMBERS",
                    "status": "unlocked",
                    "value": {
                        "member_refs": [source_entity],
                        "properties": {
                            "implementation_evidence_ref": candidate.get("candidate_id"),
                        },
                    },
                },
                {
                    "id": schema_id,
                    "property_type_ref": "schema",
                    "ruleset_ref": "RULESET_SCHEMA",
                    "status": "unlocked",
                    "value": {
                        "schema_type_ref": "record",
                        "definition": {"fields": definition_fields},
                        "properties": {
                            "implementation_evidence_ref": candidate.get("candidate_id"),
                            "source_class": source_class,
                            "serializer_method": candidate.get("serializer_method"),
                        },
                    },
                },
            ],
        })

    return sorted(result, key=lambda item: item["id"])
