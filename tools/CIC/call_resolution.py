from __future__ import annotations

from collections import defaultdict
from typing import Any

from CIC.identity import canonical_file_ref, canonical_function_ref, observed_file_ref


class CallResolutionError(ValueError):
    pass


def _function_ref(path: str, qualified_name: str) -> str:
    return canonical_function_ref(path, qualified_name)


def _file_ref(path: str) -> str:
    return observed_file_ref(path)


def _walk_function(symbol: dict[str, Any], path: str):
    qualified = symbol.get("qualified_name")
    if isinstance(qualified, str) and qualified:
        yield {
            "path": path,
            "name": symbol.get("name"),
            "owner": symbol.get("owner"),
            "qualified_name": qualified,
            "function_ref": _function_ref(path, qualified),
            "parameters": symbol.get("parameters") if isinstance(symbol.get("parameters"), list) else [],
            "logic": symbol.get("logic") if isinstance(symbol.get("logic"), dict) else {},
        }
    for nested in symbol.get("nested_functions", []):
        if isinstance(nested, dict):
            yield from _walk_function(nested, path)


def _function_inventory(ir: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    functions: list[dict[str, Any]] = []
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file_record in ir.get("files", []):
        if not isinstance(file_record, dict) or not isinstance(file_record.get("path"), str):
            continue
        path = file_record["path"]
        language_ir = file_record.get("language_ir")
        if not isinstance(language_ir, dict):
            continue
        for symbol in language_ir.get("symbols", []):
            if not isinstance(symbol, dict):
                continue
            if symbol.get("kind") == "function":
                for item in _walk_function(symbol, path):
                    functions.append(item)
                    by_file[path].append(item)
            elif symbol.get("kind") == "class":
                for method in symbol.get("methods", []):
                    if not isinstance(method, dict):
                        continue
                    for item in _walk_function(method, path):
                        functions.append(item)
                        by_file[path].append(item)
    return functions, by_file


def _reference_by_source(ir: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in ir.get("reference_evidence", []):
        if isinstance(item, dict) and isinstance(item.get("provenance"), str):
            grouped[item["provenance"]].append(item)
    for items in grouped.values():
        items.sort(key=lambda item: str(item.get("evidence_id") or ""))
    return grouped


def _language_records_by_path(ir: dict[str, Any], field: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for file_record in ir.get("files", []):
        if not isinstance(file_record, dict) or not isinstance(file_record.get("path"), str):
            continue
        language_ir = file_record.get("language_ir")
        value = language_ir.get(field) if isinstance(language_ir, dict) else None
        if isinstance(value, list):
            result[file_record["path"]] = [item for item in value if isinstance(item, dict)]
    return result


def _exported_function_map(
    exports_by_path: dict[str, list[dict[str, Any]]],
    by_file: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, tuple[str, ...]]]:
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for path, exports in exports_by_path.items():
        function_names = {item["qualified_name"] for item in by_file.get(path, [])}
        candidates: dict[str, set[str]] = defaultdict(set)
        for record in exports:
            if record.get("kind") != "local_export":
                continue
            exported = record.get("exported_name")
            target = record.get("target_qualified_name")
            if not isinstance(exported, str) or not exported or not isinstance(target, str) or not target:
                continue
            if target in function_names:
                candidates[exported].add(target)
        result[path] = {exported: tuple(sorted(values)) for exported, values in candidates.items()}
    return result


def _resolved_import_bindings(
    path: str,
    language_id: str,
    imports: list[dict[str, Any]],
    references: list[dict[str, Any]],
    exported_functions: dict[str, dict[str, tuple[str, ...]]],
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    symbols: dict[str, tuple[str, str]] = {}
    namespaces: dict[str, str] = {}
    ref_by_index = {
        int(str(item.get("evidence_id")).rsplit("::", 1)[1]): item
        for item in references
        if isinstance(item.get("evidence_id"), str)
        and str(item.get("evidence_id")).rsplit("::", 1)[-1].isdigit()
    }

    for index, record in enumerate(imports):
        reference = ref_by_index.get(index)
        if not reference or reference.get("resolution_status") != "RESOLVED":
            continue
        target_file_ref = reference.get("target_entity_ref")
        if not isinstance(target_file_ref, str) or not target_file_ref.startswith("FILE::"):
            continue
        target_path = target_file_ref.removeprefix("FILE::")

        if language_id == "python":
            if record.get("kind") == "import":
                module = record.get("module")
                alias = record.get("alias")
                if isinstance(alias, str) and alias:
                    namespaces[alias] = target_path
                elif isinstance(module, str) and module:
                    namespaces[module] = target_path
            elif record.get("kind") == "from_import":
                for name_record in record.get("names", []):
                    if not isinstance(name_record, dict):
                        continue
                    imported = name_record.get("name")
                    local = name_record.get("alias") or imported
                    if isinstance(imported, str) and imported and isinstance(local, str) and local:
                        symbols[local] = (target_path, imported)

        elif language_id in {"javascript", "typescript"} and record.get("kind") == "import":
            target_exports = exported_functions.get(target_path, {})
            for name_record in record.get("names", []):
                if not isinstance(name_record, dict):
                    continue
                local = name_record.get("local")
                imported = name_record.get("imported")
                kind = name_record.get("kind")
                if not isinstance(local, str) or not local:
                    continue
                if kind == "ImportNamespaceSpecifier":
                    namespaces[local] = target_path
                    continue
                if kind not in {"ImportSpecifier", "ImportDefaultSpecifier"}:
                    continue
                exported_name = "default" if kind == "ImportDefaultSpecifier" else imported
                if not isinstance(exported_name, str) or not exported_name:
                    continue
                targets = target_exports.get(exported_name, ())
                if len(targets) == 1:
                    symbols[local] = (target_path, targets[0])

    return symbols, namespaces


def _simple_binding_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value.startswith("..."):
        return None
    if any(token in value for token in (".", "[", "]", "{", "}", "(", ")", ",", " ")):
        return None
    return value


def _shadowed_names(source: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for parameter in source.get("parameters", []):
        if not isinstance(parameter, dict):
            continue
        name = _simple_binding_name(parameter.get("name"))
        if name:
            names.add(name)
    logic = source.get("logic") if isinstance(source.get("logic"), dict) else {}
    for write in logic.get("writes", []):
        if isinstance(write, dict):
            name = _simple_binding_name(write.get("name"))
            if name:
                names.add(name)
    for assignment in logic.get("assignments", []):
        if not isinstance(assignment, dict):
            continue
        for target in assignment.get("targets", []):
            name = _simple_binding_name(target)
            if name:
                names.add(name)
    return names


def _function_matches(functions: list[dict[str, Any]], qualified_name: str) -> list[dict[str, Any]]:
    return [function for function in functions if function["qualified_name"] == qualified_name]


def _same_file_candidates(
    source: dict[str, Any],
    target: str,
    by_file: dict[str, list[dict[str, Any]]],
    shadowed: set[str],
) -> list[dict[str, Any]]:
    functions = by_file.get(source["path"], [])

    if "." not in target:
        child_name = f"{source['qualified_name']}.<locals>.{target}"
        child = _function_matches(functions, child_name)
        if child:
            return child

        owner = source.get("owner")
        if isinstance(owner, str) and "<locals>" in owner:
            sibling = _function_matches(functions, f"{owner}.{target}")
            if sibling:
                return sibling

        if target in shadowed:
            return []
        return _function_matches(functions, target)

    if target.startswith("self.") or target.startswith("this."):
        owner = source.get("owner")
        method = target.split(".", 1)[1]
        if isinstance(owner, str) and owner and ".<locals>" not in owner:
            return _function_matches(functions, f"{owner}.{method}")
    return []


def _import_candidates(
    target: str,
    symbol_bindings: dict[str, tuple[str, str]],
    namespace_bindings: dict[str, str],
    exported_functions: dict[str, dict[str, tuple[str, ...]]],
    by_file: dict[str, list[dict[str, Any]]],
    shadowed: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    if "." not in target and target not in shadowed:
        direct = symbol_bindings.get(target)
        if direct:
            path, target_name = direct
            for function in by_file.get(path, []):
                if function["qualified_name"] == target_name and function["function_ref"] not in seen:
                    result.append(function)
                    seen.add(function["function_ref"])

    for namespace in sorted(namespace_bindings, key=len, reverse=True):
        if namespace in shadowed:
            continue
        prefix = f"{namespace}."
        if not target.startswith(prefix):
            continue
        target_name = target[len(prefix):]
        path = namespace_bindings[namespace]
        export_map = exported_functions.get(path)
        allowed_names = export_map.get(target_name, ()) if export_map is not None else (target_name,)
        for allowed_name in allowed_names:
            for function in by_file.get(path, []):
                if function["qualified_name"] == allowed_name and function["function_ref"] not in seen:
                    result.append(function)
                    seen.add(function["function_ref"])
        if result:
            break
    return result


def resolve_function_calls(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve Function calls to canonical Function Property refs without promoting Links."""
    if not isinstance(ir, dict) or not isinstance(ir.get("files"), list):
        raise CallResolutionError("CIC Code IR requires files array")

    functions, by_file = _function_inventory(ir)
    references = _reference_by_source(ir)
    imports_by_path = _language_records_by_path(ir, "imports")
    exports_by_path = _language_records_by_path(ir, "exports")
    exported_functions = _exported_function_map(exports_by_path, by_file)
    language_by_path = {
        item["path"]: item.get("language_ir", {}).get("language_id")
        for item in ir["files"]
        if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("language_ir"), dict)
    }

    evidence: list[dict[str, Any]] = []
    for source in functions:
        path = source["path"]
        calls = source.get("logic", {}).get("calls", [])
        if not isinstance(calls, list):
            continue
        shadowed = _shadowed_names(source)
        symbol_bindings, namespace_bindings = _resolved_import_bindings(
            path,
            str(language_by_path.get(path) or ""),
            imports_by_path.get(path, []),
            references.get(path, []),
            exported_functions,
        )

        for index, call in enumerate(calls):
            if not isinstance(call, dict):
                continue
            target = call.get("target")
            target_text = target if isinstance(target, str) and target else None
            candidates: list[dict[str, Any]] = []
            if target_text:
                candidates.extend(_same_file_candidates(source, target_text, by_file, shadowed))
                for candidate in _import_candidates(
                    target_text,
                    symbol_bindings,
                    namespace_bindings,
                    exported_functions,
                    by_file,
                    shadowed,
                ):
                    if all(existing["function_ref"] != candidate["function_ref"] for existing in candidates):
                        candidates.append(candidate)

            if len(candidates) == 1:
                status = "RESOLVED"
                reason = "EXACT_FUNCTION_SURFACE"
                resolved = candidates[0]
            elif len(candidates) > 1:
                status = "UNRESOLVED"
                reason = "AMBIGUOUS_FUNCTION_SURFACE"
                resolved = None
            else:
                status = "UNRESOLVED"
                reason = "NO_PROVEN_FUNCTION_SURFACE"
                resolved = None

            span = call.get("span") if isinstance(call.get("span"), dict) else {}
            evidence.append({
                "call_id": f"CALL::{path}::{source['qualified_name']}::{index}",
                "source_file_ref": _file_ref(path),
                "source_canonical_file_ref": canonical_file_ref(path),
                "source_function_ref": source["function_ref"],
                "target_file_ref": _file_ref(resolved["path"]) if resolved else None,
                "target_canonical_file_ref": canonical_file_ref(resolved["path"]) if resolved else None,
                "target_function_ref": resolved["function_ref"] if resolved else None,
                "target_expression": target_text,
                "resolution_status": status,
                "resolution_reason": reason,
                "candidate_function_refs": [item["function_ref"] for item in candidates],
                "shadowed_names": sorted(shadowed),
                "function_property_scope": "#FILE",
                "function_refs_are_property_refs": True,
                "observed_file_refs_preserve_source_suffix": True,
                "canonical_file_refs_are_language_agnostic": True,
                "canonical_link_status": "UNRESOLVED",
                "canonical_semantic_authority": False,
                "line": span.get("line"),
                "provenance": path,
                "evidence_kind": "implementation_function_call",
                "cic_ir": dict(call),
            })

    return evidence
