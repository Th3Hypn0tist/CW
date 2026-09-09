from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from CIC.cw import CWValidationError, file_refs, filetree, links, load_cw, validate_cw
from CIC.event_causality import EventCausalityError, evaluate_code_event_causality
from CIC.identity import canonical_file_key_from_ref


REPORT_VERSION = "1.1"


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _identity_index(document: dict[str, Any]) -> dict[str, tuple[str, str | None, dict[str, Any]]]:
    index: dict[str, tuple[str, str | None, dict[str, Any]]] = {}
    for entity in document.get("entities", []):
        if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
            continue
        entity_id = entity["id"]
        index[entity_id] = ("entity", None, entity)
        for prop in entity.get("properties", []):
            if isinstance(prop, dict) and isinstance(prop.get("id"), str):
                index[prop["id"]] = ("property", entity_id, prop)
    return index


def _properties(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    for entity in document.get("entities", []):
        if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
            continue
        for prop in entity.get("properties", []):
            if isinstance(prop, dict):
                result.append((entity["id"], prop))
    return result


def _canonical_file_paths(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        result.append(canonical_file_key_from_ref(ref))
    return result


def _max_file_depth(refs: list[str]) -> int:
    depths = [len(PurePosixPath(path).parts) for path in _canonical_file_paths(refs)]
    return max(depths, default=0)


def _top_level_file_entries(refs: list[str]) -> list[str]:
    values = {PurePosixPath(path).parts[0] for path in _canonical_file_paths(refs) if PurePosixPath(path).parts}
    return sorted(values, key=str.lower)


def _gap_summary(document: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    explicit: list[dict[str, Any]] = []
    for index, gap in enumerate(document.get("gaps", [])):
        if isinstance(gap, dict):
            explicit.append(deepcopy(gap))
        else:
            explicit.append({"id": f"GAP::{index}", "value": deepcopy(gap)})

    unresolved_status_refs: list[str] = []
    for entity in document.get("entities", []):
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        status = entity.get("status")
        if isinstance(status, str) and status.lower() in {"unresolved", "unsolved", "invalid"}:
            unresolved_status_refs.append(str(entity_id))
        for prop in entity.get("properties", []):
            if not isinstance(prop, dict):
                continue
            prop_status = prop.get("status")
            if isinstance(prop_status, str) and prop_status.lower() in {"unresolved", "unsolved", "invalid"}:
                unresolved_status_refs.append(str(prop.get("id")))
    return explicit, sorted(set(unresolved_status_refs))


def build_cw_report(document: dict[str, Any], *, source: str | None = None) -> dict[str, Any]:
    validate_cw(document)
    snapshot = deepcopy(document)
    identity = document.get("identity") if isinstance(document.get("identity"), dict) else {}
    format_block = document.get("format") if isinstance(document.get("format"), dict) else {}
    serialization = document.get("serialization") if isinstance(document.get("serialization"), dict) else {}
    shards = document.get("shards") if isinstance(document.get("shards"), list) else []
    entities = [entity for entity in document.get("entities", []) if isinstance(entity, dict)]
    property_records = _properties(document)
    index = _identity_index(document)

    entity_types = Counter(str(entity.get("entity_type_ref") or "<missing>") for entity in entities)
    property_types = Counter(str(prop.get("property_type_ref") or "<missing>") for _, prop in property_records)
    rulesets = Counter(str(prop.get("ruleset_ref") or "<missing>") for _, prop in property_records)

    file_identities = file_refs(document)
    file_tree_status = "NOT_APPLICABLE"
    file_tree_error: str | None = None
    if file_identities:
        try:
            filetree(document)
            file_tree_status = "PASS"
        except CWValidationError as exc:
            file_tree_status = "FAIL"
            file_tree_error = str(exc)

    link_records = links(document)
    link_types = Counter(str(item.get("link_type_ref") or "<missing>") for item in link_records)
    link_rulesets = Counter(str(item.get("ruleset_ref") or "<missing>") for item in link_records)
    property_endpoint_links = 0
    entity_endpoint_links = 0
    mixed_endpoint_links = 0
    for item in link_records:
        parent_kind = index.get(str(item.get("parent_ref")), (None, None, {}))[0]
        child_kind = index.get(str(item.get("child_ref")), (None, None, {}))[0]
        if parent_kind == "property" and child_kind == "property":
            property_endpoint_links += 1
        elif parent_kind == "entity" and child_kind == "entity":
            entity_endpoint_links += 1
        else:
            mixed_endpoint_links += 1

    functions: list[dict[str, Any]] = []
    decomposition = Counter()
    for owner_ref, prop in property_records:
        if prop.get("property_type_ref") != "function":
            continue
        value = prop.get("value") if isinstance(prop.get("value"), dict) else {}
        details = value.get("properties") if isinstance(value.get("properties"), dict) else {}
        state = str(details.get("decomposition_state") or "unspecified")
        decomposition[state] += 1
        functions.append({
            "id": prop.get("id"),
            "owner_ref": owner_ref,
            "function_type_ref": value.get("function_type_ref"),
            "qualified_name": details.get("qualified_name") or details.get("name"),
            "decomposition_state": state,
        })

    code_profile = identity.get("type") == "code_model"
    event_items: list[dict[str, Any]] = []
    event_status = Counter()
    event_errors: list[dict[str, str]] = []
    events_with_handlers = 0
    events_with_effects = 0
    for owner_ref, prop in property_records:
        if prop.get("property_type_ref") != "event" or not isinstance(prop.get("id"), str):
            continue
        value = prop.get("value") if isinstance(prop.get("value"), dict) else {}
        item: dict[str, Any] = {
            "id": prop["id"],
            "owner_ref": owner_ref,
            "event_type_ref": value.get("event_type_ref"),
            "causality_status": "NOT_EVALUATED",
            "handler_targets": [],
            "effect_refs": [],
        }
        if code_profile:
            try:
                result = evaluate_code_event_causality(document, prop["id"])
                item["causality_status"] = result.status
                item["handler_targets"] = list(result.handler_targets)
                item["effect_refs"] = list(result.effect_refs)
                event_status[result.status] += 1
                if result.handler_targets:
                    events_with_handlers += 1
                if result.effect_refs:
                    events_with_effects += 1
            except EventCausalityError as exc:
                item["causality_status"] = "FAIL"
                event_status["FAIL"] += 1
                event_errors.append({"event_ref": prop["id"], "error": str(exc)})
        else:
            event_status["NOT_EVALUATED"] += 1
        event_items.append(item)

    explicit_gaps, unresolved_status_refs = _gap_summary(document)
    unsolved_events = [item["id"] for item in event_items if item.get("causality_status") == "UNSOLVED"]

    issues: list[dict[str, Any]] = []
    if file_tree_status == "FAIL":
        issues.append({"kind": "FILE_TREE", "severity": "FAIL", "detail": file_tree_error})
    for error in event_errors:
        issues.append({"kind": "EVENT_CAUSALITY", "severity": "FAIL", **error})
    for event_ref in unsolved_events:
        issues.append({"kind": "EVENT_CAUSALITY", "severity": "UNSOLVED", "event_ref": event_ref})
    for ref in unresolved_status_refs:
        issues.append({"kind": "STATUS", "severity": "UNSOLVED", "ref": ref})
    for gap in explicit_gaps:
        issues.append({"kind": "GAP", "severity": "UNSOLVED", "gap": deepcopy(gap)})

    if any(issue.get("severity") == "FAIL" for issue in issues):
        verdict = "FAIL"
    elif issues:
        verdict = "UNSOLVED"
    else:
        verdict = "PASS"

    report = {
        "report_version": REPORT_VERSION,
        "source": source,
        "verdict": verdict,
        "document": {
            "identity_id": identity.get("id"),
            "name": identity.get("name"),
            "type": identity.get("type"),
            "version": identity.get("version"),
            "status": document.get("status"),
            "contract_format": format_block.get("contract_format"),
            "format_version": format_block.get("format_version"),
            "specification_ref": document.get("specification_ref"),
            "purpose": document.get("purpose"),
        },
        "serialization": {
            "mode": serialization.get("mode") or ("cw_file_shards" if shards else "single_document"),
            "shard_count": len(shards),
            "assembled_from_shards": bool(serialization.get("assembled_from_shards")),
            "source_suffix_in_shard_name": serialization.get("source_suffix_in_shard_name"),
        },
        "integrity": {
            "status": "PASS",
            "validator": "CIC.validate_cw",
            "canonical_identity_count": len(index),
            "dangling_link_refs": 0,
        },
        "entities": {
            "total": len(entities),
            "by_type": _sorted_counter(entity_types),
            "file_entities": len(file_identities),
        },
        "properties": {
            "total": len(property_records),
            "by_type": _sorted_counter(property_types),
            "by_ruleset": _sorted_counter(rulesets),
        },
        "files": {
            "applicable": bool(file_identities),
            "count": len(file_identities),
            "tree_status": file_tree_status,
            "max_depth": _max_file_depth(file_identities),
            "top_level_entries": _top_level_file_entries(file_identities),
            "error": file_tree_error,
        },
        "functions": {
            "total": len(functions),
            "by_decomposition_state": _sorted_counter(decomposition),
            "items": functions,
        },
        "events": {
            "total": len(event_items),
            "code_profile_evaluated": code_profile,
            "by_causality_status": _sorted_counter(event_status),
            "with_explicit_handler": events_with_handlers if code_profile else None,
            "with_explicit_effect": events_with_effects if code_profile else None,
            "items": event_items,
        },
        "links": {
            "total": len(link_records),
            "by_type": _sorted_counter(link_types),
            "by_ruleset": _sorted_counter(link_rulesets),
            "entity_to_entity": entity_endpoint_links,
            "property_to_property": property_endpoint_links,
            "mixed_endpoints": mixed_endpoint_links,
        },
        "unresolved": {
            "explicit_gap_count": len(explicit_gaps),
            "explicit_gaps": explicit_gaps,
            "status_ref_count": len(unresolved_status_refs),
            "status_refs": unresolved_status_refs,
            "unsolved_event_count": len(unsolved_events),
            "unsolved_event_refs": unsolved_events,
        },
        "issues": issues,
    }

    if document != snapshot:
        raise RuntimeError("CW report generation must not mutate input")
    return report


def report_cw(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    document = load_cw(candidate)
    return build_cw_report(document, source=str(candidate))


def _counter_lines(values: dict[str, int], *, indent: str = "  ") -> list[str]:
    if not values:
        return [f"{indent}<none>"]
    return [f"{indent}{key}: {value}" for key, value in values.items()]


def format_cw_report(report: dict[str, Any]) -> str:
    document = report["document"]
    serialization = report.get("serialization", {})
    entities = report["entities"]
    properties = report["properties"]
    files = report["files"]
    functions = report["functions"]
    events = report["events"]
    link_info = report["links"]
    unresolved = report["unresolved"]
    issues = report["issues"]

    lines = [
        "CW REPORT",
        "=========",
        f"Source: {report.get('source') or '<memory>'}",
        f"VERDICT: {report['verdict']}",
        "",
        "Document",
        f"  identity: {document.get('identity_id')}",
        f"  name: {document.get('name')}",
        f"  type: {document.get('type')}",
        f"  version: {document.get('version')}",
        f"  status: {document.get('status')}",
        f"  format: {document.get('contract_format')} {document.get('format_version')}",
        f"  specification: {document.get('specification_ref')}",
        "",
        "Serialization",
        f"  mode: {serialization.get('mode')}",
        f"  shards: {serialization.get('shard_count', 0)}",
        f"  assembled: {'yes' if serialization.get('assembled_from_shards') else 'no'}",
        "",
        "Integrity",
        f"  CW: {report['integrity']['status']}",
        f"  canonical identities: {report['integrity']['canonical_identity_count']}",
        f"  dangling Link refs: {report['integrity']['dangling_link_refs']}",
        "",
        "Entities",
        f"  total: {entities['total']}",
        f"  #FILE: {entities['file_entities']}",
        "  by type:",
        *_counter_lines(entities["by_type"], indent="    "),
        "",
        "Properties",
        f"  total: {properties['total']}",
        "  by type:",
        *_counter_lines(properties["by_type"], indent="    "),
        "",
        "#FILE topology",
        f"  applicable: {'yes' if files['applicable'] else 'no'}",
        f"  count: {files['count']}",
        f"  tree: {files['tree_status']}",
        f"  max depth: {files['max_depth']}",
    ]
    if files["top_level_entries"]:
        lines.append(f"  top-level: {', '.join(files['top_level_entries'])}")
    if files.get("error"):
        lines.append(f"  error: {files['error']}")

    lines.extend([
        "",
        "Functions",
        f"  total: {functions['total']}",
        "  decomposition:",
        *_counter_lines(functions["by_decomposition_state"], indent="    "),
        "",
        "Events",
        f"  total: {events['total']}",
        f"  code-profile causality: {'evaluated' if events['code_profile_evaluated'] else 'not applicable'}",
        "  by status:",
        *_counter_lines(events["by_causality_status"], indent="    "),
    ])
    if events["code_profile_evaluated"]:
        lines.extend([
            f"  explicit handlers: {events['with_explicit_handler']}",
            f"  explicit effects: {events['with_explicit_effect']}",
        ])

    lines.extend([
        "",
        "Links",
        f"  total: {link_info['total']}",
        "  by type:",
        *_counter_lines(link_info["by_type"], indent="    "),
        f"  entity -> entity: {link_info['entity_to_entity']}",
        f"  property -> property: {link_info['property_to_property']}",
        f"  mixed endpoints: {link_info['mixed_endpoints']}",
        "",
        "Unresolved / Gaps",
        f"  explicit gaps: {unresolved['explicit_gap_count']}",
        f"  unresolved status refs: {unresolved['status_ref_count']}",
        f"  unsolved Events: {unresolved['unsolved_event_count']}",
    ])

    if issues:
        lines.extend(["", "Issues"])
        for issue in issues:
            severity = issue.get("severity", "INFO")
            kind = issue.get("kind", "UNKNOWN")
            if "event_ref" in issue:
                detail = issue["event_ref"]
            elif "ref" in issue:
                detail = issue["ref"]
            elif "detail" in issue:
                detail = issue["detail"]
            elif "gap" in issue:
                gap = issue["gap"]
                detail = gap.get("id") if isinstance(gap, dict) else str(gap)
            else:
                detail = ""
            lines.append(f"  [{severity}] {kind}: {detail}")

    lines.extend(["", f"VERDICT: {report['verdict']}"])
    return "\n".join(lines)