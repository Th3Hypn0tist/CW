from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

try:
    from .cw_condition_validate import validate_event_condition_value
    from .cw_dispatch_validate import validate_emit_statement, validate_event_dispatch_link
    from .cw_effect_validate import validate_effect_semantics
except ImportError:
    from cw_condition_validate import validate_event_condition_value
    from cw_dispatch_validate import validate_emit_statement, validate_event_dispatch_link
    from cw_effect_validate import validate_effect_semantics


@dataclass
class Finding:
    severity: str
    code: str
    path: str
    message: str


class Findings:
    def __init__(self) -> None:
        self.items: list[Finding] = []

    def error(self, code: str, path: Path | str, message: str) -> None:
        self.items.append(Finding("ERROR", code, str(path), message))

    @property
    def ok(self) -> bool:
        return not any(item.severity == "ERROR" for item in self.items)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _canonical_rel(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be non-empty string")
    if "\\" in value or unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"non-canonical path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"invalid relative path: {value!r}")
    return str(path)


def _under(root: Path, rel: str) -> Path:
    relative = PurePosixPath(_canonical_rel(rel))
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink is not canonical: {rel}")
    resolved_root = root.resolve()
    resolved = current.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path escapes root: {rel}")
    return resolved


def _family(entity_id: str) -> str | None:
    if not entity_id.startswith("#") or ":" not in entity_id:
        return None
    return entity_id[1:].split(":", 1)[0]


def _encoded_id(entity_id: str) -> str:
    return quote(entity_id, safe="-._~")


def _property_key(owner: str, property_id: str) -> str:
    return owner + "\0" + property_id


def _resolve_ref(
    ref: Any,
    local_owner: str | None,
    entities: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(ref, dict) and set(ref) == {"entity_ref", "property_ref"}:
        entity_ref = ref.get("entity_ref")
        property_ref = ref.get("property_ref")
        if isinstance(entity_ref, str) and isinstance(property_ref, str):
            return properties.get(_property_key(entity_ref, property_ref))
        return None
    if not isinstance(ref, str) or not ref:
        return None
    if ref in entities:
        return entities[ref]
    if local_owner is not None:
        return properties.get(_property_key(local_owner, ref))
    return None


def _walk_refs(value: Any, names: set[str]) -> list[Any]:
    refs: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and (
                isinstance(item, str)
                or (isinstance(item, dict) and set(item) == {"entity_ref", "property_ref"})
            ):
                refs.append(item)
            refs.extend(_walk_refs(item, names))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_walk_refs(item, names))
    return refs


def _walk_logic(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("op"), str):
            out.append(value)
        for item in value.values():
            out.extend(_walk_logic(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_walk_logic(item))
    return out


def validate_package(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root).expanduser().resolve()
    f = Findings()

    try:
        cw = _read_json(root / "Format" / "CW.json")
        ccf = _read_json(root / "Format" / "CCF.json")
        dr = _read_json(root / "Format" / "DR.json")
    except Exception as exc:
        return {
            "result": "INVALID_PACKAGE",
            "errors": 1,
            "findings": [asdict(Finding("ERROR", "FORMAT_LOAD_FAILED", str(root), str(exc)))],
        }

    format_root = root / "Format"
    model_root = root / str(cw.get("model_root", "Model"))
    manifest_path = root / str(cw.get("model_closure", {}).get("manifest", "Model/model.cw"))

    for field, expected in (("ccf_ref", "CCF.json"), ("dr_ref", "DR.json")):
        try:
            ref = _canonical_rel(cw.get(field, expected))
            path = _under(format_root, ref)
            if not path.is_file():
                f.error("FORMAT_REF_MISSING", path, field)
        except Exception as exc:
            f.error("FORMAT_REF_INVALID", format_root, f"{field}: {exc}")

    nodetype_root = format_root / str(cw.get("nodetypes_ref", "NodeTypes"))
    nodetypes: dict[str, dict[str, Any]] = {}
    family_dirs: set[str] = set()
    if nodetype_root.is_dir():
        family_dirs = {p.name for p in nodetype_root.iterdir() if p.is_dir() and not p.is_symlink()}
        for path in sorted(nodetype_root.rglob("*.cwn")):
            try:
                node = _read_json(path)
                node_id = node.get("id")
                if not isinstance(node_id, str) or not node_id.startswith("CWN::"):
                    f.error("NODETYPE_ID_INVALID", path, repr(node_id))
                    continue
                public_id = node_id[len("CWN::"):].replace("::", "/")
                if public_id in nodetypes:
                    f.error("NODETYPE_ID_DUPLICATE", path, public_id)
                nodetypes[public_id] = node
            except Exception as exc:
                f.error("NODETYPE_LOAD_FAILED", path, str(exc))
    else:
        f.error("NODETYPE_ROOT_MISSING", nodetype_root, "Format/NodeTypes missing")

    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        f.error("MODEL_MANIFEST_LOAD_FAILED", manifest_path, str(exc))
        manifest = {"shards": []}

    declared: dict[str, str] = {}
    records = manifest.get("shards", []) if isinstance(manifest.get("shards"), list) else []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            f.error("SHARD_ENTRY_INVALID", manifest_path, f"shards[{index}]")
            continue
        entity_ref = record.get("entity_ref")
        artifact_ref = record.get("artifact_ref")
        if not isinstance(entity_ref, str) or not entity_ref:
            f.error("SHARD_ENTITY_REF_INVALID", manifest_path, f"shards[{index}]")
            continue
        try:
            artifact_ref = _canonical_rel(artifact_ref)
        except Exception as exc:
            f.error("SHARD_ARTIFACT_REF_INVALID", manifest_path, str(exc))
            continue
        if entity_ref in declared:
            f.error("SHARD_ENTITY_DUPLICATE", manifest_path, entity_ref)
        if artifact_ref in declared.values():
            f.error("SHARD_ARTIFACT_DUPLICATE", manifest_path, artifact_ref)
        declared[entity_ref] = artifact_ref

    actual = {
        path.relative_to(model_root).as_posix()
        for path in model_root.rglob("*.cw")
        if path.is_file() and path.resolve() != manifest_path.resolve()
    } if model_root.is_dir() else set()
    if set(declared.values()) != actual:
        for item in sorted(actual - set(declared.values())):
            f.error("SHARD_UNLISTED", model_root / item, item)
        for item in sorted(set(declared.values()) - actual):
            f.error("SHARD_MISSING", model_root / item, item)

    entities: dict[str, dict[str, Any]] = {}
    owners: dict[str, str] = {}
    source_paths: dict[str, Path] = {}
    properties: dict[str, dict[str, Any]] = {}

    for entity_ref, artifact_ref in declared.items():
        path = model_root / artifact_ref
        try:
            entity = _read_json(path)
        except Exception as exc:
            f.error("SHARD_LOAD_FAILED", path, str(exc))
            continue
        if entity.get("id") != entity_ref:
            f.error("SHARD_ID_MISMATCH", path, f"{entity.get('id')!r} != {entity_ref!r}")
            continue
        if entity_ref in entities:
            f.error("ENTITY_ID_DUPLICATE", path, entity_ref)
        entities[entity_ref] = entity
        source_paths[entity_ref] = path
        family = _family(entity_ref)
        if family is None or family not in family_dirs:
            f.error("ENTITY_FAMILY_UNREGISTERED", path, entity_ref)
        node_type = entity.get("entity_type_ref")
        if not isinstance(node_type, str) or node_type not in nodetypes:
            f.error("ENTITY_NODETYPE_UNREGISTERED", path, repr(node_type))
        elif family is not None and node_type.split("/", 1)[0] != family:
            f.error("ENTITY_NODETYPE_FAMILY_MISMATCH", path, f"{entity_ref} -> {node_type}")
        props = entity.get("properties")
        if not isinstance(props, list):
            f.error("ENTITY_PROPERTIES_INVALID", path, entity_ref)
            continue
        local_ids: set[str] = set()
        for prop in props:
            if not isinstance(prop, dict):
                f.error("PROPERTY_INVALID", path, entity_ref)
                continue
            prop_id = prop.get("id")
            if not isinstance(prop_id, str) or not prop_id:
                f.error("PROPERTY_ID_INVALID", path, entity_ref)
                continue
            if prop_id in local_ids:
                f.error("PROPERTY_ID_DUPLICATE", path, f"{entity_ref}: {prop_id}")
                continue
            local_ids.add(prop_id)
            prop_key = _property_key(entity_ref, prop_id)
            properties[prop_key] = prop
            owners[prop_key] = entity_ref
            source_paths[prop_key] = path
    property_rules = {r.get("id"): r for r in dr.get("property_rulesets", []) if isinstance(r, dict) and isinstance(r.get("id"), str)}
    link_rules = {r.get("id"): r for r in dr.get("link_rulesets", []) if isinstance(r, dict) and isinstance(r.get("id"), str)}
    file_types = {r.get("id"): r for r in dr.get("asset_file_types", []) if isinstance(r, dict) and isinstance(r.get("id"), str)}
    schema_types = {item for item in dr.get("schema_types", []) if isinstance(item, str) and item}
    primitives = set(dr.get("logic_primitive_set", {}).get("primitives", []))
    forbidden_ops = set(dr.get("logic_primitive_set", {}).get("forbidden", []))
    forbidden_links = set(dr.get("forbidden_link_types", []))

    for prop_key, prop in properties.items():
        prop_id = prop.get("id")
        owner = owners[prop_key]
        path = source_paths[prop_key]
        prop_type = prop.get("property_type_ref")
        ruleset_ref = prop.get("ruleset_ref")
        rule = property_rules.get(ruleset_ref)
        link_rule = link_rules.get(ruleset_ref)
        selected = link_rule if prop_type == "link" else rule
        if not isinstance(selected, dict):
            f.error("RULESET_UNRESOLVED", path, f"{prop_id}: {ruleset_ref!r}")
            continue
        if selected.get("property_type_ref") != prop_type:
            f.error("RULESET_PROPERTY_TYPE_MISMATCH", path, prop_id)
        value = prop.get("value")
        if not isinstance(value, dict):
            f.error("PROPERTY_VALUE_INVALID", path, prop_id)
            continue
        for field in selected.get("required_fields", []) if isinstance(selected.get("required_fields"), list) else []:
            if field not in value:
                f.error("PROPERTY_REQUIRED_FIELD_MISSING", path, f"{prop_id}.{field}")

        if prop_type == "members":
            for ref in value.get("member_refs", []) if isinstance(value.get("member_refs"), list) else []:
                if ref not in entities:
                    f.error("MEMBER_REF_UNRESOLVED", path, f"{prop_id}: {ref}")

        elif prop_type == "data":
            schema_ref = value.get("schema_ref")
            target = _resolve_ref(schema_ref, owner, entities, properties) if schema_ref is not None else None
            if schema_ref is not None and (not isinstance(target, dict) or target.get("property_type_ref") != "schema"):
                f.error("DATA_SCHEMA_REF_INVALID", path, f"{prop_id}: {schema_ref!r}")

        elif prop_type == "schema":
            schema_type = value.get("schema_type_ref")
            if schema_types and schema_type not in schema_types:
                f.error("SCHEMA_TYPE_UNREGISTERED", path, f"{prop_id}: {schema_type!r}")
            definition = value.get("definition")
            for ref in _walk_refs(definition, {"schema_ref", "item_schema_ref", "value_schema_ref"}):
                target = _resolve_ref(ref, owner, entities, properties)
                if not isinstance(target, dict) or target.get("property_type_ref") != "schema":
                    f.error("SCHEMA_REF_INVALID", path, f"{prop_id}: {ref!r}")
            if schema_type == "map":
                if not isinstance(definition, dict) or definition.get("value_schema_ref") is None:
                    f.error("SCHEMA_MAP_VALUE_SCHEMA_MISSING", path, prop_id)

        elif prop_type == "function":
            local_properties = {
                item.get("id"): item
                for key, item in properties.items()
                if owners.get(key) == owner and isinstance(item.get("id"), str)
            }
            for ref in [*(value.get("input_refs") or []), *(value.get("output_refs") or [])]:
                target = _resolve_ref(ref, owner, entities, properties)
                if not isinstance(ref, str) or not isinstance(target, dict):
                    f.error("FUNCTION_REF_UNRESOLVED", path, f"{prop_id}: {ref!r}")
            logic = value.get("logic")
            if isinstance(logic, dict):
                for stmt in _walk_logic(logic):
                    op = stmt.get("op")
                    if op in forbidden_ops or op not in primitives:
                        f.error("LOGIC_OP_INVALID", path, f"{prop_id}: {op!r}")
                    if op == "emit":
                        for finding in validate_emit_statement(
                            stmt,
                            containing_function_ref=prop_id,
                            properties=local_properties,
                        ):
                            f.error(finding["code"], path, f"{prop_id}: {finding['message']}")

        elif prop_type == "link":
            link_type = value.get("link_type_ref")
            if link_type in forbidden_links:
                f.error("LINK_TYPE_FORBIDDEN", path, f"{prop_id}: {link_type}")
            if selected.get("link_type_ref") != link_type:
                f.error("LINK_RULESET_TYPE_MISMATCH", path, prop_id)
            for field in ("parent_ref", "child_ref"):
                ref = value.get(field)
                if _resolve_ref(ref, owner, entities, properties) is None:
                    f.error("LINK_ENDPOINT_UNRESOLVED", path, f"{prop_id}.{field}: {ref!r}")
            if link_type == "event_condition":
                for finding in validate_event_condition_value(value, selected):
                    f.error(finding["code"], path, f"{prop_id}: {finding['message']}")
            elif link_type == "event_dispatch":
                local_properties = {
                    item.get("id"): item
                    for key, item in properties.items()
                    if owners.get(key) == owner and isinstance(item.get("id"), str)
                }
                for finding in validate_event_dispatch_link(value, local_properties, entities):
                    f.error(finding["code"], path, f"{prop_id}: {finding['message']}")

        elif prop_type == "asset":
            owner = owners[prop_key]
            owner_family = _family(owner)
            asset_ref = value.get("asset_ref")
            file_type_ref = value.get("file_type_ref")
            try:
                canonical = _canonical_rel(asset_ref)
                asset_path = _under(root, canonical)
                expected_dir = f"Assets/{owner_family}"
                if not canonical.startswith(expected_dir + "/"):
                    f.error("ASSET_FAMILY_PATH_INVALID", path, f"{prop_id}: {canonical}")
                if not asset_path.is_file():
                    f.error("ASSET_MISSING", asset_path, prop_id)
                record = file_types.get(file_type_ref)
                if not isinstance(record, dict):
                    f.error("ASSET_FILE_TYPE_UNREGISTERED", path, f"{prop_id}: {file_type_ref!r}")
                else:
                    exts = record.get("extensions", [])
                    if asset_path.suffix not in exts:
                        f.error("ASSET_EXTENSION_INVALID", asset_path, f"{asset_path.suffix} not in {exts}")
                    expected_name = _encoded_id(owner) + asset_path.suffix
                    if asset_path.name != expected_name:
                        f.error("ASSET_BASENAME_INVALID", asset_path, f"expected {expected_name}")
            except Exception as exc:
                f.error("ASSET_REF_INVALID", path, f"{prop_id}: {exc}")

    for entity_id, entity in entities.items():
        assets = [p for p in entity.get("properties", []) if isinstance(p, dict) and p.get("property_type_ref") == "asset"]
        if len(assets) > 1:
            f.error("ASSET_CARDINALITY_INVALID", source_paths[entity_id], f"{entity_id}: {len(assets)}")

    links = [(key, p) for key, p in properties.items() if p.get("property_type_ref") == "link"]

    for effect_key, effect in properties.items():
        if effect.get("property_type_ref") != "effect":
            continue
        effect_id = effect.get("id")
        effect_owner = owners[effect_key]
        effect_value = effect.get("value") if isinstance(effect.get("value"), dict) else {}
        target_values = []
        for link_key, link in links:
            if owners[link_key] != effect_owner:
                continue
            link_value = link.get("value") if isinstance(link.get("value"), dict) else {}
            if link_value.get("link_type_ref") == "effect_target" and link_value.get("parent_ref") == effect_id:
                target_values.append(link_value)
        for finding in validate_effect_semantics(effect_value, target_values, dr):
            f.error(finding["code"], source_paths[effect_key], f"{effect_id}: {finding['message']}")

    for req_key, req in properties.items():
        if req.get("property_type_ref") != "required_link":
            continue
        req_id = req.get("id")
        path = source_paths[req_key]
        value = req.get("value") if isinstance(req.get("value"), dict) else {}
        owner = owners[req_key]
        self_endpoint = value.get("self_endpoint")
        matches = []
        for link_key, link in links:
            if owners[link_key] != owner:
                continue
            lv = link.get("value") if isinstance(link.get("value"), dict) else {}
            if lv.get("required_link_ref") != req_id:
                continue
            matches.append(link)
            if self_endpoint in {"parent_ref", "child_ref"} and lv.get(self_endpoint) != owner:
                f.error("REQUIRED_LINK_OWNER_ENDPOINT_MISMATCH", source_paths[link_key], f"{link.get('id')} -> {req_id}")
            if lv.get("link_type_ref") != value.get("link_type_ref"):
                f.error("REQUIRED_LINK_TYPE_MISMATCH", source_paths[link_key], f"{link.get('id')} -> {req_id}")
        minimum = value.get("min", 0)
        maximum = value.get("max")
        if isinstance(minimum, int) and len(matches) < minimum:
            f.error("REQUIRED_LINK_MIN_UNSATISFIED", path, f"{req_id}: {len(matches)} < {minimum}")
        if isinstance(maximum, int) and len(matches) > maximum:
            f.error("REQUIRED_LINK_MAX_EXCEEDED", path, f"{req_id}: {len(matches)} > {maximum}")

    if manifest.get("specification_ref") != "LOCAL_FORMAT:Format":
        f.error("SPECIFICATION_REF_INVALID", manifest_path, repr(manifest.get("specification_ref")))
    format_version = manifest.get("format", {}).get("format_version") if isinstance(manifest.get("format"), dict) else None
    if format_version != ccf.get("version"):
        f.error("CCF_VERSION_MISMATCH", manifest_path, f"{format_version!r} != {ccf.get('version')!r}")

    return {
        "result": "READY" if f.ok else "INVALID_PACKAGE",
        "errors": sum(item.severity == "ERROR" for item in f.items),
        "entities": len(entities),
        "properties": len(properties),
        "shards": len(declared),
        "findings": [asdict(item) for item in f.items],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_package(args.package)
    except Exception as exc:
        report = {
            "result": "IMPLEMENTATION_FAILURE",
            "errors": 1,
            "findings": [asdict(Finding("ERROR", "IMPLEMENTATION_FAILURE", str(args.package), str(exc)))],
        }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"RESULT: {report['result']}")
        for item in report["findings"]:
            print(f"{item['severity']} {item['code']} {item['path']}: {item['message']}")
    return 0 if report["result"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
