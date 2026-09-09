from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .api import DEFAULT_EXCLUDED_DIRS, _normalize_relative, _read_text, _walk_source_files, import_files
from .cw import CWValidationError, validate_cw
from .diagnostics import summarize_diagnostics


def _function_properties(cw: dict[str, Any]) -> list[dict[str, Any]]:
    return [prop for entity in cw.get("entities", []) if isinstance(entity, dict) for prop in entity.get("properties", []) if isinstance(prop, dict) and prop.get("property_type_ref") == "function"]


def _resolution_summary(records: Any, *, target_key: str, canonical_target_key: str | None = None) -> dict[str, Any]:
    items = [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []
    status: Counter[str] = Counter(); reasons: Counter[str] = Counter(); targets: set[str] = set(); canonical: set[str] = set(); unresolved=[]
    for item in items:
        state=str(item.get("resolution_status") or "UNKNOWN"); reason=str(item.get("resolution_reason") or "UNKNOWN"); status[state]+=1; reasons[reason]+=1; target=item.get(target_key)
        if state=="RESOLVED" and isinstance(target,str) and target:
            targets.add(target)
            if canonical_target_key and isinstance(item.get(canonical_target_key),str): canonical.add(item[canonical_target_key])
        elif state!="RESOLVED": unresolved.append({"id":item.get("call_id") or item.get("evidence_id"),"source":item.get("source_function_ref") or item.get("source_entity_ref"),"target_expression":item.get("target_expression") or item.get("target_reference"),"reason":reason,"candidates":item.get("candidate_function_refs") or item.get("candidate_paths") or []})
    result={"total":len(items),"by_status":dict(sorted(status.items())),"by_reason":dict(sorted(reasons.items())),"resolved_targets":sorted(targets),"unresolved":unresolved}
    if canonical_target_key: result["resolved_canonical_targets"]=sorted(canonical)
    return result


def scan_folder(code_folder: str | Path, *, excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS) -> dict[str, Any]:
    root=Path(code_folder).expanduser().resolve()
    if not root.is_dir(): raise ValueError(f"code folder not found: {root}")
    source_paths=_walk_source_files(root,excluded_dirs); text_files=[]; skipped=[]
    for source_path in source_paths:
        relative=_normalize_relative(source_path,root); source=_read_text(source_path)
        if source is None: skipped.append(relative)
        else: text_files.append({"path":relative,"content":source})
    bundle=import_files(text_files); languages=Counter(); parsers=Counter(); imports=0
    for record in bundle.ir.get("files",[]):
        lir=record.get("language_ir") if isinstance(record,dict) else None
        if not isinstance(lir,dict): continue
        language=str(lir.get("language_id") or "unclassified"); languages[language]+=1; parsers["available" if lir.get("parser_available") else "unavailable"]+=1; imports+=len(lir.get("imports",[])) if isinstance(lir.get("imports"),list) else 0
    functions=_function_properties(bundle.cw); nested=0; partial=0
    for prop in functions:
        value=prop.get("value") if isinstance(prop.get("value"),dict) else {}; details=value.get("properties") if isinstance(value.get("properties"),dict) else {}
        if isinstance(details.get("owner"),str) and "<locals>" in details["owner"]: nested+=1
        if details.get("decomposition_state")!="complete": partial+=1
    try: validate_cw(bundle.cw); gate="PASS"; error=None
    except CWValidationError as exc: gate="FAIL"; error=str(exc)
    return {"kind":"cic_corpus_scan","version":"0.4.0","root":str(root),"files":{"seen":len(source_paths),"text_imported":bundle.files_imported,"binary_skipped":len(skipped),"file_entities":len(bundle.cw.get("entities",[]))},"languages":dict(sorted(languages.items())),"parsers":dict(sorted(parsers.items())),"functions":{"properties":len(functions),"nested":nested,"not_fully_decomposed":partial},"imports":imports,"references":_resolution_summary(bundle.ir.get("reference_evidence",[]),target_key="target_entity_ref",canonical_target_key="target_canonical_entity_ref"),"calls":_resolution_summary(bundle.ir.get("call_evidence",[]),target_key="target_function_ref",canonical_target_key="target_canonical_file_ref"),"events":{"candidates":len(bundle.ir.get("event_candidates",[])),"materialized":len(bundle.ir.get("event_materialization",[]))},"solver":dict(bundle.ir.get("solver",{})),"diagnostics":summarize_diagnostics(bundle.ir.get("files",[])),"cw_gate_b":{"status":gate,"error":error},"skipped_binary":skipped,"policy":{"same_import_chain_as_import_folder":True,"zero_semantic_guessing":True,"scan_is_not_canonical_authority":True}}
