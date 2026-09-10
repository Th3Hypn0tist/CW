from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.CodeImport.model import CodeEdge, CodeImportResult, CodeNode


DEFAULT_SPECIFICATION_REF = "CW_CORE@1.1.0"


def _safe_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())
    return value or "CODE_IMPORT"


def _canonical_ref(ref: str) -> str:
    if ref.startswith("file:"):
        return "FILE::" + _safe_id(ref[5:])
    if ref.startswith("function:"):
        return "FUNC::" + _safe_id(ref[9:])
    if ref.startswith("module:"):
        return "MODULE::" + _safe_id(ref[7:])
    if ref.startswith("callable:"):
        return "CALLABLE::" + _safe_id(ref[9:])
    return _safe_id(ref)


def _owner_file_ref(node: CodeNode) -> str | None:
    if node.kind == "file":
        return node.ref
    if node.kind == "function" and node.source_path is not None:
        return None
    return None


def _function_owner_ref(function_ref: str, result: CodeImportResult) -> str | None:
    node = result.nodes.get(function_ref)
    if node is None or node.source_path is None:
        return None
    candidates = [
        other.ref
        for other in result.nodes.values()
        if other.kind == "file" and other.source_path == node.source_path
    ]
    return sorted(candidates)[0] if candidates else None


def _edge_owner_ref(edge: CodeEdge, result: CodeImportResult) -> str | None:
    parent = result.nodes.get(edge.parent_ref)
    if parent is None:
        return None
    if parent.kind == "file":
        return parent.ref
    if parent.kind == "function":
        return _function_owner_ref(parent.ref, result)
    return parent.ref


def to_cw_document(
    result: CodeImportResult,
    *,
    specification_ref: str = DEFAULT_SPECIFICATION_REF,
    identity_id: str | None = None,
    identity_name: str | None = None,
    version: str = "0.1.0",
) -> dict[str, Any]:
    """Convert parser IR into an unlocked CW artifact.

    Parser IR stays independent of CW serialization. Code files become explicit
    ``code`` Entities, functions become ``function`` Properties on their source
    file Entity, and parser relations become generic canonical Link Properties
    preserving their explicit relation labels. No relation meaning is inferred.
    """

    source_name = result.source.name or "Code Import"
    artifact_id = identity_id or f"CODE_IMPORT::{_safe_id(source_name)}"
    artifact_name = identity_name or f"Code Import: {source_name}"

    entities: dict[str, dict[str, Any]] = {}
    ref_map = {ref: _canonical_ref(ref) for ref in result.nodes}

    for node in sorted(result.nodes.values(), key=lambda item: item.ref):
        canonical_ref = ref_map[node.ref]
        if node.kind == "function":
            continue
        entity_type = "code" if node.kind == "file" else "generic"
        entity: dict[str, Any] = {
            "id": canonical_ref,
            "name": node.name,
            "entity_type_ref": entity_type,
            "status": "unlocked",
            "properties": [],
        }
        if entity_type == "code":
            entity["required_links"] = []
        entities[node.ref] = entity

    for node in sorted(result.nodes.values(), key=lambda item: item.ref):
        if node.kind != "function":
            continue
        owner_ref = _function_owner_ref(node.ref, result)
        owner = entities.get(owner_ref or "")
        if owner is None:
            continue
        owner["properties"].append(
            {
                "id": ref_map[node.ref],
                "property_type_ref": "function",
                "ruleset_ref": "RULESET_FUNCTION",
                "status": "unlocked",
                "value": {
                    "function_type_ref": "function",
                    "properties": {},
                },
            }
        )

    link_counter = 0
    for edge in sorted(
        result.edges,
        key=lambda item: (item.relation, item.parent_ref, item.child_ref, item.ref),
    ):
        parent_ref = ref_map.get(edge.parent_ref)
        child_ref = ref_map.get(edge.child_ref)
        if parent_ref is None or child_ref is None:
            continue
        owner_ref = _edge_owner_ref(edge, result)
        owner = entities.get(owner_ref or "")
        if owner is None:
            continue
        link_counter += 1
        owner["properties"].append(
            {
                "id": f"LINK::{link_counter:06d}",
                "property_type_ref": "link",
                "ruleset_ref": "RULESET_LINK",
                "status": "unlocked",
                "value": {
                    "link_type_ref": edge.relation,
                    "parent_ref": parent_ref,
                    "child_ref": child_ref,
                    "properties": {
                        "source_parser_ref": edge.ref,
                        **({"source_line": edge.line} if edge.line is not None else {}),
                    },
                },
            }
        )

    return {
        "format": {
            "contract_format": "CANONICAL_CONTRACT",
            "format_version": "2.1",
        },
        "identity": {
            "id": artifact_id,
            "name": artifact_name,
            "type": "canonical_wireframe",
            "version": version,
        },
        "specification_ref": specification_ref,
        "status": "unlocked",
        "purpose": "Represent code structure imported by a modular source parser without inventing semantics beyond explicit parser output.",
        "scope": {
            "owns": ["imported code structure", "explicit parser-produced relations"],
            "does_not_own": ["source code", "runtime behavior not established by the parser"],
        },
        "entities": list(entities.values()),
        "constraints": {"invariants": []},
        "references": [],
        "gaps": [
            {
                "id": f"IMPORT_FINDING::{index:04d}",
                "description": finding.message,
                "source": str(finding.source_path),
                **({"line": finding.line} if finding.line is not None else {}),
            }
            for index, finding in enumerate(result.findings, start=1)
        ],
        "prose": {
            "summary": "CW generated from modular code-import parser output.",
            "notes": "Imported artifact is unlocked. Parser output is canonicalized only through explicit fields; filenames and paths are serialization/source provenance, not semantic authority.",
        },
    }


def export_cw(
    result: CodeImportResult,
    destination: Path,
    *,
    specification_ref: str = DEFAULT_SPECIFICATION_REF,
) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = to_cw_document(result, specification_ref=specification_ref)
    destination.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination
