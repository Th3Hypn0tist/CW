#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from .cw_spec_common import read_json, resolve_bundle
    from .cw_compose import compose_documents
    from .cw_version import validate_entity_version
    from . import cw_spec_lint
except ImportError:
    from cw_spec_common import read_json, resolve_bundle
    from cw_compose import compose_documents
    from cw_version import validate_entity_version
    import cw_spec_lint

VER = "2.4.0"


@dataclass
class F:
    severity: str
    code: str
    file: str
    path: str
    message: str


class C:
    def __init__(self) -> None:
        self.f: list[F] = []

    def add(self, severity: str, code: str, file: Path, path: str, message: str) -> None:
        self.f.append(F(severity, code, str(file), path, message))

    def e(self, code: str, file: Path, path: str, message: str) -> None:
        self.add("ERROR", code, file, path, message)

    def u(self, code: str, file: Path, path: str, message: str) -> None:
        self.add("UNREADY", code, file, path, message)


def dl(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def artifact_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise FileNotFoundError(root)
    paths = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".cw", ".json"}]
    return sorted(paths, key=lambda path: (path.as_posix().casefold(), path.as_posix()))


def split_union(description: str) -> list[str]:
    out, depth, start = [], 0, 0
    for index, char in enumerate(description):
        depth += char == "<"
        depth -= char == ">"
        if char == "|" and depth == 0:
            out.append(description[start:index])
            start = index + 1
    out.append(description[start:])
    return [item.strip() for item in out]


def type_matches(value: Any, description: Any) -> bool:
    if not isinstance(description, str):
        return True
    options = split_union(description)
    if len(options) > 1:
        return any(type_matches(value, option) for option in options)
    if description == "null":
        return value is None
    if description == "string" or description.endswith("_ref"):
        return isinstance(value, str) and bool(value)
    if description in {"logic_value", "logic_statement", "logic_representation", "required_link_ref"}:
        return isinstance(value, dict)
    if description == "endpoint_constraint":
        return isinstance(value, dict)
    if description == "non_negative_integer":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if description == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if description == "boolean":
        return isinstance(value, bool)
    if description == "object":
        return isinstance(value, dict)
    if description.startswith("array<") and description.endswith(">"):
        return isinstance(value, list) and all(type_matches(item, description[6:-1]) for item in value)
    return True


def validate_schema(value: Any, schema_def: Any, c: C, file: Path, path: str, name: str) -> None:
    if not isinstance(schema_def, dict):
        return
    if not isinstance(value, dict):
        c.e("VALUE_NOT_OBJECT", file, path, name + " must be object")
        return
    fields = schema_def.get("fields", {}) if isinstance(schema_def.get("fields"), dict) else {}
    for field in schema_def.get("required", []) if isinstance(schema_def.get("required"), list) else []:
        if field not in value:
            c.e("VALUE_REQUIRED_FIELD_MISSING", file, path + "." + field, f"{name} requires {field!r}")
    for field, description in fields.items():
        if field in value and not type_matches(value[field], description):
            c.e("VALUE_TYPE_MISMATCH", file, path + "." + field, f"expected {description!r}")


def effective_sections(nodetype: str, registry: dict[str, dict], cache: dict[str, list[str]], stack=None) -> list[str]:
    if nodetype in cache:
        return cache[nodetype]
    stack = list(stack or [])
    if nodetype in stack:
        raise ValueError("NodeType inheritance cycle")
    stack.append(nodetype)
    result: list[str] = []
    for parent in registry[nodetype].get("extends", []):
        for section in effective_sections(parent, registry, cache, stack):
            if section not in result:
                result.append(section)
    for section in registry[nodetype].get("sections", []):
        if section not in result:
            result.append(section)
    cache[nodetype] = result
    return result


def inherits(nodetype: str, wanted: str, registry: dict[str, dict]) -> bool:
    if nodetype == wanted:
        return True
    seen: set[str] = set()
    stack = [nodetype]
    while stack:
        current = stack.pop()
        if current in seen or current not in registry:
            continue
        seen.add(current)
        for parent in registry[current].get("extends", []):
            if parent == wanted:
                return True
            stack.append(parent)
    return False


def endpoint_constraint_matches(
    constraint: Any,
    endpoint_ref: Any,
    objects: dict[str, tuple[str, dict, Path]],
    nodetypes: dict[str, dict],
) -> bool | None:
    """Evaluate the established Required Link other_endpoint constraint shape.

    Returns True/False when the opposite endpoint resolves, or None when its
    canonical target is unresolved and compatibility therefore cannot be proven.
    """
    if constraint is None:
        return True
    if not isinstance(constraint, dict) or not constraint:
        return False
    allowed_fields = {"entity_nodetype_ref", "property_type_ref"}
    if set(constraint) - allowed_fields:
        return False
    entity_nodetype_ref = constraint.get("entity_nodetype_ref")
    property_type_ref = constraint.get("property_type_ref")
    if entity_nodetype_ref is None and property_type_ref is None:
        return False
    if entity_nodetype_ref is not None and (not isinstance(entity_nodetype_ref, str) or entity_nodetype_ref not in nodetypes):
        return False
    if property_type_ref is not None and (not isinstance(property_type_ref, str) or not property_type_ref):
        return False

    target = objects.get(endpoint_ref)
    if target is None:
        return None
    kind, value, _ = target
    if entity_nodetype_ref is not None:
        target_nodetype = value.get("entity_type_ref") if kind == "Entity" else None
        if not isinstance(target_nodetype, str) or not inherits(target_nodetype, entity_nodetype_ref, nodetypes):
            return False
    if property_type_ref is not None:
        if kind != "Property" or value.get("property_type_ref") != property_type_ref:
            return False
    return True


def required_fields(c: C, file: Path, value: Any, fields: Any, path: str, code: str) -> None:
    if not isinstance(value, dict) or not isinstance(fields, list):
        return
    for field in fields:
        if isinstance(field, str) and field not in value:
            c.e(code, file, path + "." + field, f"missing {field!r}")


def _validate_ref_array(
    value: Any,
    schema_def: dict[str, Any],
    objects: dict[str, tuple[str, dict, Path]],
    c: C,
    file: Path,
    path: str,
) -> None:
    if not isinstance(value, list):
        c.e("NODE_SECTION_ARRAY_INVALID", file, path, "must be an array")
        return
    seen: set[str] = set()
    allowed = schema_def.get("allowed_canonical_kinds")
    for index, ref in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(ref, str) or not ref:
            c.e("NODE_SECTION_REF_INVALID", file, item_path, repr(ref))
            continue
        if schema_def.get("duplicate_refs") == "invalid_model" and ref in seen:
            c.e("NODE_SECTION_REF_DUPLICATE", file, item_path, ref)
        seen.add(ref)
        target = objects.get(ref)
        if target is None:
            c.u("NODE_SECTION_REF_UNRESOLVED", file, item_path, ref)
            continue
        if isinstance(allowed, list) and target[0] not in allowed:
            c.e("NODE_SECTION_REF_KIND_INCOMPATIBLE", file, item_path, target[0])


def _validate_entity_sections(
    entity: dict[str, Any],
    sections: list[str],
    readers: dict[str, Any],
    node_ruleset: dict[str, Any],
    objects: dict[str, tuple[str, dict, Path]],
    c: C,
    file: Path,
    path: str,
) -> None:
    for section in sections:
        reader = readers.get(section)
        if not isinstance(reader, dict) or reader.get("kind") != "entity_field":
            continue
        field = reader.get("field")
        if not isinstance(field, str):
            continue
        if field not in entity:
            if reader.get("required") is True:
                c.u("NODE_SECTION_REQUIRED_FIELD_MISSING", file, path + "." + field, section)
            continue
        schema_ref = reader.get("reader")
        schema_def = node_ruleset.get(schema_ref) if isinstance(schema_ref, str) else None
        if isinstance(schema_def, dict) and schema_def.get("shape") == "array<canonical_ref>":
            _validate_ref_array(entity[field], schema_def, objects, c, file, path + "." + field)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--spec-set", type=Path)
    parser.add_argument("--ccf", type=Path)
    parser.add_argument("--nodetypes", type=Path)
    parser.add_argument("--rulesets", type=Path)
    parser.add_argument("--spec-dir", type=Path)
    parser.add_argument("--skip-spec-lint", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        bundle = resolve_bundle(
            spec_set=args.spec_set,
            ccf=args.ccf,
            nodetypes=args.nodetypes,
            rulesets=args.rulesets,
            spec_dir=args.spec_dir,
            default_start=Path(__file__).parent,
        )
    except Exception as exc:
        print(f"RESULT: IMPLEMENTATION_FAILURE\n{exc}", file=sys.stderr)
        return 2

    if not args.skip_spec_lint:
        specification_findings = cw_spec_lint.lint_bundle(bundle)
        if any(item.severity == "ERROR" for item in specification_findings.f):
            print("RESULT: INVALID_SPECIFICATION", file=sys.stderr)
            return 1

    c = C()
    try:
        paths = artifact_paths(args.input)
        documents = compose_documents(paths, read_json)
        nodetypes = {item["id"]: item for item in dl(bundle.nodetypes.get("nodetypes")) if isinstance(item.get("id"), str)}
        property_rulesets = {item["id"]: item for item in dl(bundle.rulesets.get("property_rulesets")) if isinstance(item.get("id"), str)}
        link_rulesets = {item["id"]: item for item in dl(bundle.rulesets.get("link_rulesets")) if isinstance(item.get("id"), str)}
        node_ruleset = bundle.rulesets.get("node_ruleset", {})
        readers = node_ruleset.get("section_readers", {}) if isinstance(node_ruleset, dict) else {}
        primitive_sets = {item["id"]: item for item in dl(bundle.rulesets.get("logic_primitive_sets")) if isinstance(item.get("id"), str)}
        contract_shape = bundle.ccf.get("contract_shape", {})
        entity_shape = contract_shape.get("entities", {}) if isinstance(contract_shape, dict) else {}
        entity_required = entity_shape.get("item_required", []) if isinstance(entity_shape, dict) else []
        property_shape = entity_shape.get("properties", {}) if isinstance(entity_shape, dict) else {}
        property_required = property_shape.get("item_required", []) if isinstance(property_shape, dict) else []

        objects: dict[str, tuple[str, dict, Path]] = {}
        owners: dict[str, str] = {}
        for file, document in documents:
            required_fields(c, file, document, contract_shape.get("required", []), "$", "CONTRACT_REQUIRED_FIELD_MISSING")
            for entity_index, entity in enumerate(document.get("entities", []) if isinstance(document.get("entities"), list) else []):
                if not isinstance(entity, dict):
                    c.e("ENTITY_NOT_OBJECT", file, f"$.entities[{entity_index}]", "Entity must be object")
                    continue
                entity_path = f"$.entities[{entity_index}]"
                required_fields(c, file, entity, entity_required, entity_path, "ENTITY_REQUIRED_FIELD_MISSING")
                version_error = validate_entity_version(entity)
                if version_error:
                    c.e("NODE_VERSION_INVALID", file, entity_path, version_error)
                entity_id = entity.get("id")
                if isinstance(entity_id, str):
                    if entity_id in objects:
                        c.e("CANONICAL_ID_DUPLICATE", file, entity_path + ".id", entity_id)
                    objects[entity_id] = ("Entity", entity, file)
                    owners[entity_id] = entity_id
                properties = entity.get("properties")
                if properties is not None and not isinstance(properties, list):
                    c.e("ENTITY_PROPERTIES_INVALID", file, entity_path + ".properties", "properties must be array")
                    continue
                for property_index, prop in enumerate(properties or []):
                    if not isinstance(prop, dict):
                        c.e("PROPERTY_NOT_OBJECT", file, f"{entity_path}.properties[{property_index}]", "Property must be object")
                        continue
                    property_path = f"{entity_path}.properties[{property_index}]"
                    required_fields(c, file, prop, property_required, property_path, "PROPERTY_REQUIRED_FIELD_MISSING")
                    property_id = prop.get("id")
                    if isinstance(property_id, str):
                        if property_id in objects:
                            c.e("CANONICAL_ID_DUPLICATE", file, property_path + ".id", property_id)
                        objects[property_id] = ("Property", prop, file)
                        if isinstance(entity_id, str):
                            owners[property_id] = entity_id

        section_cache: dict[str, list[str]] = {}
        links: list[dict[str, Any]] = []
        for file, document in documents:
            for entity_index, entity in enumerate(document.get("entities", []) if isinstance(document.get("entities"), list) else []):
                if not isinstance(entity, dict):
                    continue
                entity_path = f"$.entities[{entity_index}]"
                nodetype = entity.get("entity_type_ref")
                if nodetype not in nodetypes:
                    c.e("NODETYPE_UNRESOLVED", file, entity_path + ".entity_type_ref", repr(nodetype))
                    sections = []
                else:
                    sections = effective_sections(nodetype, nodetypes, section_cache)
                _validate_entity_sections(entity, sections, readers, node_ruleset, objects, c, file, entity_path)

                for property_index, prop in enumerate(entity.get("properties", []) if isinstance(entity.get("properties"), list) else []):
                    if not isinstance(prop, dict):
                        continue
                    property_path = f"{entity_path}.properties[{property_index}]"
                    property_type = prop.get("property_type_ref")
                    ruleset_ref = prop.get("ruleset_ref")
                    ruleset = link_rulesets.get(ruleset_ref) if property_type == "link" else property_rulesets.get(ruleset_ref)
                    if ruleset is None:
                        c.e("RULESET_REF_UNRESOLVED", file, property_path + ".ruleset_ref", repr(ruleset_ref))
                        continue
                    if ruleset.get("property_type_ref") != property_type:
                        c.e("RULESET_TYPE_MISMATCH", file, property_path + ".ruleset_ref", str(property_type))
                    validate_schema(prop.get("value"), ruleset.get("value_schema"), c, file, property_path + ".value", str(ruleset_ref))
                    value = prop.get("value")
                    if not isinstance(value, dict):
                        continue

                    constraints = ruleset.get("reference_constraints", {}) if isinstance(ruleset.get("reference_constraints"), dict) else {}
                    for field, policy in constraints.items():
                        values = value.get(field)
                        values = values if isinstance(values, list) else [values]
                        for ref_index, ref in enumerate(values):
                            if ref is None:
                                continue
                            ref_path = property_path + f".value.{field}[{ref_index}]"
                            target = objects.get(ref)
                            if target is None:
                                c.u("CANONICAL_REFERENCE_UNRESOLVED", file, ref_path, repr(ref))
                                continue
                            kind, target_value, _ = target
                            allowed_kinds = policy.get("allowed_canonical_kinds") if isinstance(policy, dict) else None
                            if isinstance(allowed_kinds, list) and kind not in allowed_kinds:
                                c.e("REFERENCE_KIND_INCOMPATIBLE", file, ref_path, kind)
                            allowed_property_types = policy.get("allowed_property_type_refs") if isinstance(policy, dict) else None
                            if kind == "Property" and isinstance(allowed_property_types, list) and target_value.get("property_type_ref") not in allowed_property_types:
                                c.e("REFERENCE_PROPERTY_INCOMPATIBLE", file, ref_path, str(target_value.get("property_type_ref")))
                            allowed_nodetypes = policy.get("allowed_nodetype_refs") if isinstance(policy, dict) else None
                            if kind == "Entity" and isinstance(allowed_nodetypes, list):
                                target_nodetype = target_value.get("entity_type_ref")
                                if not isinstance(target_nodetype, str) or not any(inherits(target_nodetype, wanted, nodetypes) for wanted in allowed_nodetypes):
                                    c.e("REFERENCE_NODETYPE_INCOMPATIBLE", file, ref_path, str(target_nodetype))

                    if property_type == "link":
                        links.append(prop)
                        relation = value.get("link_type_ref")
                        if ruleset.get("relation_policy", "fixed") != "open" and relation != ruleset.get("link_type_ref"):
                            c.e("LINK_RELATION_RULESET_MISMATCH", file, property_path + ".value.link_type_ref", str(relation))
                        if ruleset.get("relation_policy") == "open" and isinstance(relation, str) and relation.startswith("#"):
                            topology = objects.get(relation)
                            topology_rule = ruleset.get("relation_resolution", {}).get("canonical_topology_ref", {}) if isinstance(ruleset.get("relation_resolution"), dict) else {}
                            required_nodetype = topology_rule.get("target_nodetype_ref") if isinstance(topology_rule, dict) else None
                            if topology is None:
                                c.u("LINK_TOPOLOGY_REF_UNRESOLVED", file, property_path + ".value.link_type_ref", relation)
                            else:
                                kind, target_value, _ = topology
                                target_nodetype = target_value.get("entity_type_ref") if kind == "Entity" else None
                                compatible = kind == "Entity" and isinstance(target_nodetype, str)
                                if compatible and isinstance(required_nodetype, str):
                                    compatible = inherits(target_nodetype, required_nodetype, nodetypes)
                                if not compatible:
                                    c.e("LINK_TOPOLOGY_REF_INCOMPATIBLE", file, property_path + ".value.link_type_ref", relation)

                        endpoint_constraints = ruleset.get("endpoint_constraints", {}) if isinstance(ruleset.get("endpoint_constraints"), dict) else {}
                        for side in ("parent_ref", "child_ref"):
                            ref = value.get(side)
                            target = objects.get(ref)
                            if target is None:
                                c.u("LINK_ENDPOINT_UNRESOLVED", file, property_path + ".value." + side, repr(ref))
                                continue
                            constraints_for_side = endpoint_constraints.get(side, [])
                            if constraints_for_side:
                                kind, target_value, _ = target
                                compatible = False
                                for constraint in constraints_for_side:
                                    if constraint.startswith("property:") and kind == "Property" and target_value.get("property_type_ref") == constraint.split(":", 1)[1]:
                                        compatible = True
                                    if constraint.startswith("entity_nodetype:") and kind == "Entity" and isinstance(target_value.get("entity_type_ref"), str) and inherits(target_value["entity_type_ref"], constraint.split(":", 1)[1], nodetypes):
                                        compatible = True
                                if not compatible:
                                    c.e("LINK_ENDPOINT_INCOMPATIBLE", file, property_path + ".value." + side, str(constraints_for_side))

                    if property_type == "function" and isinstance(value.get("logic"), dict):
                        logic = value["logic"]
                        validate_schema(logic, ruleset.get("logic_schema"), c, file, property_path + ".value.logic", str(ruleset_ref))
                        if primitive_sets.get(logic.get("primitive_set_ref")) is None:
                            c.e("LOGIC_PRIMITIVE_SET_UNRESOLVED", file, property_path + ".value.logic.primitive_set_ref", repr(logic.get("primitive_set_ref")))

        by_requirement: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
        for link in links:
            value = link.get("value", {})
            requirement_ref = value.get("required_link_ref") if isinstance(value, dict) else None
            if isinstance(requirement_ref, dict):
                by_requirement.setdefault((requirement_ref.get("entity_ref"), requirement_ref.get("required_link_id")), []).append(link)

        for file, document in documents:
            for entity_index, entity in enumerate(document.get("entities", []) if isinstance(document.get("entities"), list) else []):
                if not isinstance(entity, dict) or entity.get("entity_type_ref") not in nodetypes:
                    continue
                if "required_links" not in effective_sections(entity["entity_type_ref"], nodetypes, section_cache):
                    continue
                for requirement_index, requirement in enumerate(entity.get("required_links", []) if isinstance(entity.get("required_links"), list) else []):
                    requirement_path = f"$.entities[{entity_index}].required_links[{requirement_index}]"
                    validate_schema(requirement, node_ruleset.get("required_link_schema"), c, file, requirement_path, "Required Link")
                    if not isinstance(requirement, dict):
                        continue
                    minimum = requirement.get("min")
                    maximum = requirement.get("max")
                    if isinstance(minimum, int) and isinstance(maximum, int) and maximum < minimum:
                        c.e("REQUIRED_LINK_CARDINALITY_INVALID", file, requirement_path, f"max {maximum} < min {minimum}")
                    constraint = requirement.get("other_endpoint")
                    if constraint is not None:
                        if not isinstance(constraint, dict) or not constraint or set(constraint) - {"entity_nodetype_ref", "property_type_ref"}:
                            c.e("REQUIRED_LINK_ENDPOINT_CONSTRAINT_INVALID", file, requirement_path + ".other_endpoint", repr(constraint))
                        else:
                            entity_constraint = constraint.get("entity_nodetype_ref")
                            property_constraint = constraint.get("property_type_ref")
                            if entity_constraint is None and property_constraint is None:
                                c.e("REQUIRED_LINK_ENDPOINT_CONSTRAINT_INVALID", file, requirement_path + ".other_endpoint", "constraint is empty")
                            if entity_constraint is not None and (not isinstance(entity_constraint, str) or entity_constraint not in nodetypes):
                                c.e("REQUIRED_LINK_ENDPOINT_NODETYPE_UNRESOLVED", file, requirement_path + ".other_endpoint.entity_nodetype_ref", repr(entity_constraint))
                            if property_constraint is not None and (not isinstance(property_constraint, str) or not property_constraint):
                                c.e("REQUIRED_LINK_ENDPOINT_PROPERTY_TYPE_INVALID", file, requirement_path + ".other_endpoint.property_type_ref", repr(property_constraint))

                    hits = []
                    for link in by_requirement.get((entity.get("id"), requirement.get("id")), []):
                        value = link.get("value", {})
                        side = requirement.get("self_endpoint")
                        if side not in {"parent_ref", "child_ref"}:
                            continue
                        if value.get("link_type_ref") != requirement.get("link_type_ref") or value.get(side) != entity.get("id"):
                            c.e("REQUIRED_LINK_BINDING_INCOMPATIBLE", file, requirement_path, f"bound Link {link.get('id')!r} contradicts relation or self endpoint")
                            continue
                        other_side = "child_ref" if side == "parent_ref" else "parent_ref"
                        endpoint_match = endpoint_constraint_matches(constraint, value.get(other_side), objects, nodetypes)
                        if endpoint_match is False:
                            c.e("REQUIRED_LINK_BINDING_INCOMPATIBLE", file, requirement_path, f"bound Link {link.get('id')!r} contradicts other_endpoint constraint")
                            continue
                        if endpoint_match is None:
                            continue
                        hits.append(link)
                    if isinstance(minimum, int) and len(hits) < minimum:
                        c.u("REQUIRED_LINK_UNSATISFIED", file, requirement_path, f"{len(hits)} < {minimum}")
                    if isinstance(maximum, int) and len(hits) > maximum:
                        c.e("REQUIRED_LINK_MAX_EXCEEDED", file, requirement_path, f"{len(hits)} > {maximum}")

        result = "INVALID_MODEL" if any(item.severity == "ERROR" for item in c.f) else ("UNREADY" if any(item.severity == "UNREADY" for item in c.f) else "READY")
    except Exception as exc:
        print(f"RESULT: IMPLEMENTATION_FAILURE\n{exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"validator_version": VER, "result": result, "findings": [asdict(item) for item in c.f]}, indent=2))
    else:
        print(f"CW artifact validator v{VER}\nCCF {bundle.ccf.get('version')} / NodeTypes {bundle.nodetypes.get('version')} / Rulesets {bundle.rulesets.get('version')}")
        for item in c.f:
            print(f"{item.severity} {item.code} {Path(item.file).name} {item.path}: {item.message}")
        print("\nRESULT:", result)
    return 1 if result == "INVALID_MODEL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
