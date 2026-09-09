from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from CIC.api import DEFAULT_EXCLUDED_DIRS, _normalize_relative, _read_text, _walk_source_files, import_files
from CIC.cw import CWValidationError, validate_cw
from CIC.diagnostics import summarize_diagnostics


def _function_properties(cw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        prop
        for entity in cw.get("entities", [])
        if isinstance(entity, dict)
        for prop in entity.get("properties", [])
        if isinstance(prop, dict) and prop.get("property_type_ref") == "function"
    ]


def _resolution_summary(
    records: Any,
    *,
    target_key: str,
    canonical_target_key: str | None = None,
) -> dict[str, Any]:
    items = [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []
    status: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    resolved_targets: set[str] = set()
    resolved_canonical_targets: set[str] = set()
    unresolved: list[dict[str, Any]] = []

    for item in items:
        resolution_status = str(item.get("resolution_status") or "UNKNOWN")
        resolution_reason = str(item.get("resolution_reason") or "UNKNOWN")
        status[resolution_status] += 1
        reasons[resolution_reason] += 1
        target = item.get(target_key)
        if resolution_status == "RESOLVED" and isinstance(target, str) and target:
            resolved_targets.add(target)
            canonical_target = item.get(canonical_target_key) if canonical_target_key else None
            if isinstance(canonical_target, str) and canonical_target:
                resolved_canonical_targets.add(canonical_target)
        elif resolution_status != "RESOLVED":
            unresolved.append({
                "id": item.get("call_id") or item.get("evidence_id"),
                "source": item.get("source_function_ref") or item.get("source_entity_ref"),
                "target_expression": item.get("target_expression") or item.get("target_reference"),
                "reason": resolution_reason,
                "candidates": item.get("candidate_function_refs") or item.get("candidate_paths") or [],
            })

    result = {
        "total": len(items),
        "by_status": dict(sorted(status.items())),
        "by_reason": dict(sorted(reasons.items())),
        "resolved_targets": sorted(resolved_targets),
        "unresolved": unresolved,
    }
    if canonical_target_key is not None:
        result["resolved_canonical_targets"] = sorted(resolved_canonical_targets)
    return result


def scan_folder(
    code_folder: str | Path,
    *,
    excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS,
) -> dict[str, Any]:
    """Scan a real corpus through the same CIC importer without writing artifacts."""
    root = Path(code_folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"code folder not found: {root}")

    source_paths = _walk_source_files(root, excluded_dirs)
    text_files: list[dict[str, str]] = []
    skipped_binary: list[str] = []
    for source_path in source_paths:
        relative = _normalize_relative(source_path, root)
        source = _read_text(source_path)
        if source is None:
            skipped_binary.append(relative)
            continue
        text_files.append({"path": relative, "content": source})

    bundle = import_files(text_files)
    languages: Counter[str] = Counter()
    parser_status: Counter[str] = Counter()
    imports = 0

    language_by_file: dict[str, str] = {}
    for file_record in bundle.ir.get("files", []):
        language_ir = file_record.get("language_ir") if isinstance(file_record, dict) else None
        if not isinstance(language_ir, dict):
            continue
        language_id = str(language_ir.get("language_id") or "unclassified")
        path = file_record.get("path")
        file_ref = file_record.get("file_ref")
        if isinstance(file_ref, str):
            language_by_file[file_ref] = language_id
        elif isinstance(path, str):
            language_by_file[f"FILE::{path}"] = language_id
        languages[language_id] += 1
        parser_status["available" if language_ir.get("parser_available") else "unavailable"] += 1
        imports += len(language_ir.get("imports", [])) if isinstance(language_ir.get("imports"), list) else 0

    functions = _function_properties(bundle.cw)
    nested_functions = 0
    partial_functions = 0
    for prop in functions:
        value = prop.get("value") if isinstance(prop.get("value"), dict) else {}
        details = value.get("properties") if isinstance(value.get("properties"), dict) else {}
        owner = details.get("owner")
        if isinstance(owner, str) and "<locals>" in owner:
            nested_functions += 1
        if details.get("decomposition_state") != "full":
            partial_functions += 1

    reference_summary = _resolution_summary(
        bundle.ir.get("reference_evidence", []),
        target_key="target_entity_ref",
        canonical_target_key="target_canonical_entity_ref",
    )
    call_summary = _resolution_summary(
        bundle.ir.get("call_evidence", []),
        target_key="target_function_ref",
        canonical_target_key="target_canonical_file_ref",
    )
    calls_by_language: dict[str, Counter[str]] = {}
    for item in bundle.ir.get("call_evidence", []):
        if not isinstance(item, dict):
            continue
        language = language_by_file.get(str(item.get("source_file_ref")), "unclassified")
        calls_by_language.setdefault(language, Counter())[str(item.get("resolution_status") or "UNKNOWN")] += 1
    call_summary["by_language"] = {
        language: dict(sorted(counter.items()))
        for language, counter in sorted(calls_by_language.items())
    }

    gate_b_status = "PASS"
    gate_b_error = None
    try:
        validate_cw(bundle.cw)
    except CWValidationError as exc:
        gate_b_status = "FAIL"
        gate_b_error = str(exc)

    diagnostics = summarize_diagnostics(bundle.ir.get("files", []))

    return {
        "kind": "cic_corpus_scan",
        "version": "0.3.0",
        "root": str(root),
        "files": {
            "seen": len(source_paths),
            "text_imported": bundle.files_imported,
            "binary_skipped": len(skipped_binary),
            "file_entities": len(bundle.cw.get("entities", [])),
        },
        "languages": dict(sorted(languages.items())),
        "parsers": dict(sorted(parser_status.items())),
        "functions": {
            "properties": len(functions),
            "nested": nested_functions,
            "not_fully_decomposed": partial_functions,
        },
        "imports": imports,
        "references": reference_summary,
        "calls": call_summary,
        "events": {
            "candidates": len(bundle.ir.get("event_candidates", [])),
            "materialized": len(bundle.ir.get("event_materialization", [])),
        },
        "solver": dict(bundle.ir.get("solver", {})),
        "diagnostics": diagnostics,
        "cw_gate_b": {
            "status": gate_b_status,
            "error": gate_b_error,
        },
        "skipped_binary": skipped_binary,
        "policy": {
            "same_import_chain_as_import_folder": True,
            "maximum_extraction": True,
            "zero_semantic_guessing": True,
            "observed_identity_preserves_source_suffix": True,
            "canonical_identity_is_language_agnostic": True,
            "reference_and_call_resolution_are_evidence_only": True,
            "scan_is_not_canonical_authority": True,
        },
    }
