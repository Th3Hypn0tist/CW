#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from .cw_spec_common import SpecBundle, resolve_bundle
except ImportError:
    from cw_spec_common import SpecBundle, resolve_bundle

VER = "2.1.0"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


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

    def e(self, code: str, file: Path, path: str, message: str) -> None:
        self.f.append(F("ERROR", code, str(file), path, message))


def dl(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def unique(items, key, c, file, path, kind):
    out = {}
    for index, item in enumerate(items):
        value = item.get(key)
        item_path = f"{path}[{index}].{key}"
        if not isinstance(value, str) or not value:
            c.e(kind + "_ID_INVALID", file, item_path, f"{key} must be non-empty")
        elif value in out:
            c.e(kind + "_ID_DUPLICATE", file, item_path, f"duplicate {value!r}")
        else:
            out[value] = item
    return out


def schema(value, c, file, path):
    if not isinstance(value, dict):
        c.e("SCHEMA_INVALID", file, path, "schema must be object")
        return
    required, optional, fields = value.get("required", []), value.get("optional", []), value.get("fields")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        c.e("SCHEMA_REQUIRED_INVALID", file, path + ".required", "must be string array")
        required = []
    if not isinstance(optional, list) or not all(isinstance(item, str) for item in optional):
        c.e("SCHEMA_OPTIONAL_INVALID", file, path + ".optional", "must be string array")
        optional = []
    if not isinstance(fields, dict):
        c.e("SCHEMA_FIELDS_INVALID", file, path + ".fields", "must be object")
        return
    missing = (set(required) | set(optional)) - set(fields)
    if missing:
        c.e("SCHEMA_FIELDS_MISSING", file, path + ".fields", f"missing {sorted(missing)}")


def sections(nodetype, registry, cache, stack=None):
    if nodetype in cache:
        return cache[nodetype]
    stack = list(stack or [])
    if nodetype in stack:
        raise ValueError(" -> ".join(stack + [nodetype]))
    stack.append(nodetype)
    node = registry[nodetype]
    result = []
    extends = node.get("extends", [])
    if not isinstance(extends, list) or not all(isinstance(item, str) and item for item in extends):
        raise TypeError("extends must be a string array")
    for parent in extends:
        if parent not in registry:
            raise KeyError(parent)
        for section in sections(parent, registry, cache, stack):
            if section not in result:
                result.append(section)
    own = node.get("sections")
    if not isinstance(own, list) or not all(isinstance(item, str) and item for item in own):
        raise TypeError("sections must be a string array")
    for section in own:
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


def _validate_endpoint_constraints(c, ruleset, index, nts, ptypes, rules_path):
    constraints = ruleset.get("endpoint_constraints")
    if not isinstance(constraints, dict):
        return
    for side, values in constraints.items():
        if not isinstance(values, list):
            c.e("ENDPOINT_CONSTRAINTS_INVALID", rules_path, f"$.link_rulesets[{index}].endpoint_constraints.{side}", "must be array")
            continue
        for item_index, value in enumerate(values):
            path = f"$.link_rulesets[{index}].endpoint_constraints.{side}[{item_index}]"
            if not isinstance(value, str):
                c.e("ENDPOINT_CONSTRAINT_INVALID", rules_path, path, repr(value))
            elif value.startswith("entity_nodetype:") and value.split(":", 1)[1] not in nts:
                c.e("ENDPOINT_NODETYPE_UNRESOLVED", rules_path, path, value)
            elif value.startswith("property:") and value.split(":", 1)[1] not in ptypes and value != "property:link":
                c.e("ENDPOINT_PROPERTY_UNRESOLVED", rules_path, path, value)


def lint_bundle(bundle: SpecBundle) -> C:
    c = C()
    ccf_id = bundle.ccf.get("id") or (
        "CANONICAL_CONTRACT_FORMAT" if bundle.ccf.get("type") == "canonical_contract_format" else None
    )
    if bundle.nodetypes.get("ccf_ref") != ccf_id:
        c.e("NODETYPES_CCF_REF_MISMATCH", bundle.nodetypes_path, "$.ccf_ref", f"expected {ccf_id!r}")
    if bundle.rulesets.get("ccf_ref") != ccf_id:
        c.e("RULESETS_CCF_REF_MISMATCH", bundle.rulesets_path, "$.ccf_ref", f"expected {ccf_id!r}")
    if bundle.rulesets.get("nodetypes_ref") != bundle.nodetypes.get("id"):
        c.e("RULESETS_NODETYPES_REF_MISMATCH", bundle.rulesets_path, "$.nodetypes_ref", "selected NodeTypes id mismatch")

    for document, path in ((bundle.nodetypes, bundle.nodetypes_path), (bundle.rulesets, bundle.rulesets_path)):
        version = document.get("version")
        if not isinstance(version, str) or not SEMVER.fullmatch(version):
            c.e("VERSION_INVALID", path, "$.version", "semantic x.y.z required")

    nodetype_items = dl(bundle.nodetypes.get("nodetypes"))
    nts = unique(nodetype_items, "id", c, bundle.nodetypes_path, "$.nodetypes", "NODETYPE")
    node_ruleset = bundle.rulesets.get("node_ruleset")
    readers = node_ruleset.get("section_readers") if isinstance(node_ruleset, dict) else None
    if not isinstance(node_ruleset, dict) or node_ruleset.get("id") != "RULESET_NODE" or node_ruleset.get("root") != "Entity":
        c.e("NODE_RULESET_INVALID", bundle.rulesets_path, "$.node_ruleset", "RULESET_NODE root must be Entity")
        node_ruleset = {}
        readers = {}
    if not isinstance(readers, dict):
        c.e("NODE_SECTION_READERS_INVALID", bundle.rulesets_path, "$.node_ruleset.section_readers", "must be object")
        readers = {}

    cache = {}
    for index, nodetype in enumerate(nodetype_items):
        nodetype_id = nodetype.get("id")
        if not isinstance(nodetype_id, str):
            continue
        try:
            effective = sections(nodetype_id, nts, cache)
        except Exception as exc:
            c.e("NODETYPE_INHERITANCE_INVALID", bundle.nodetypes_path, f"$.nodetypes[{index}]", str(exc))
            continue
        for section in effective:
            if section not in readers:
                c.e("NODETYPE_SECTION_UNRESOLVED", bundle.nodetypes_path, f"$.nodetypes[{index}].sections", f"{section!r} has no RULESET_NODE reader")

    properties = dl(bundle.rulesets.get("property_rulesets"))
    links = dl(bundle.rulesets.get("link_rulesets"))
    property_index = unique(properties, "id", c, bundle.rulesets_path, "$.property_rulesets", "PROPERTY_RULESET")
    link_index = unique(links, "id", c, bundle.rulesets_path, "$.link_rulesets", "LINK_RULESET")
    for duplicate in set(property_index) & set(link_index):
        c.e("RULESET_ID_DUPLICATE", bundle.rulesets_path, "$.link_rulesets", f"duplicate Ruleset id {duplicate!r}")

    property_types = set()
    for index, ruleset in enumerate(properties):
        property_type = ruleset.get("property_type_ref")
        if not isinstance(property_type, str) or not property_type:
            c.e("PROPERTY_TYPE_INVALID", bundle.rulesets_path, f"$.property_rulesets[{index}].property_type_ref", "non-empty required")
        else:
            property_types.add(property_type)
        schema(ruleset.get("value_schema"), c, bundle.rulesets_path, f"$.property_rulesets[{index}].value_schema")

    flow_items = dl(bundle.rulesets.get("flow_patterns"))
    flow_index = unique(flow_items, "id", c, bundle.rulesets_path, "$.flow_patterns", "FLOW_PATTERN")
    open_count = 0
    fixed_relations = set()
    for index, ruleset in enumerate(links):
        path = f"$.link_rulesets[{index}]"
        if ruleset.get("property_type_ref") != "link":
            c.e("LINK_PROPERTY_TYPE_INVALID", bundle.rulesets_path, path + ".property_type_ref", "must be link")
        relation = ruleset.get("link_type_ref")
        policy = ruleset.get("relation_policy", "fixed")
        if policy not in {"open", "fixed"}:
            c.e("LINK_RELATION_POLICY_INVALID", bundle.rulesets_path, path + ".relation_policy", repr(policy))
        elif policy == "open":
            open_count += 1
            if relation != "*":
                c.e("OPEN_LINK_WILDCARD_INVALID", bundle.rulesets_path, path + ".link_type_ref", "open Link must use *")
            resolution = ruleset.get("relation_resolution")
            if isinstance(resolution, dict):
                topology = resolution.get("canonical_topology_ref")
                if isinstance(topology, dict):
                    target = topology.get("target_nodetype_ref")
                    if not isinstance(target, str) or target not in nts:
                        c.e("TOPOLOGY_TARGET_NODETYPE_UNRESOLVED", bundle.rulesets_path, path + ".relation_resolution.canonical_topology_ref.target_nodetype_ref", repr(target))
        elif isinstance(relation, str):
            if relation in fixed_relations:
                c.e("LINK_RELATION_DUPLICATE", bundle.rulesets_path, path + ".link_type_ref", f"duplicate {relation!r}")
            fixed_relations.add(relation)
        else:
            c.e("LINK_RELATION_INVALID", bundle.rulesets_path, path + ".link_type_ref", repr(relation))

        schema(ruleset.get("value_schema"), c, bundle.rulesets_path, path + ".value_schema")
        _validate_endpoint_constraints(c, ruleset, index, nts, property_types, bundle.rulesets_path)
        flow = ruleset.get("flow")
        if isinstance(flow, dict):
            pattern = flow.get("pattern_ref")
            if isinstance(pattern, str) and pattern not in flow_index:
                c.e("FLOW_UNRESOLVED", bundle.rulesets_path, path + ".flow.pattern_ref", pattern)
            for case_index, case in enumerate(flow.get("cases", []) if isinstance(flow.get("cases"), list) else []):
                if isinstance(case, dict) and isinstance(case.get("pattern_ref"), str) and case["pattern_ref"] not in flow_index:
                    c.e("FLOW_UNRESOLVED", bundle.rulesets_path, f"{path}.flow.cases[{case_index}]", case["pattern_ref"])

    generic = bundle.rulesets.get("generic_link_model")
    if isinstance(generic, dict):
        if generic.get("relation_vocabulary") == "open" and open_count != 1:
            c.e("GENERIC_LINK_COUNT_INVALID", bundle.rulesets_path, "$.link_rulesets", f"exactly one open generic Link required, got {open_count}")
        generic_ref = generic.get("ruleset_ref")
        if isinstance(generic_ref, str) and generic_ref not in link_index:
            c.e("GENERIC_LINK_RULESET_UNRESOLVED", bundle.rulesets_path, "$.generic_link_model.ruleset_ref", generic_ref)

    for section, reader in readers.items():
        path = f"$.node_ruleset.section_readers.{section}"
        if not isinstance(reader, dict):
            c.e("SECTION_READER_INVALID", bundle.rulesets_path, path, "must be object")
            continue
        kind = reader.get("kind")
        if kind == "property_group":
            property_type = reader.get("property_type_ref")
            if property_type != "link" and property_type not in property_types:
                c.e("SECTION_PROPERTY_UNRESOLVED", bundle.rulesets_path, path, str(property_type))
        elif kind == "entity_field":
            field = reader.get("field")
            reader_ref = reader.get("reader")
            if not isinstance(field, str) or not field:
                c.e("SECTION_ENTITY_FIELD_INVALID", bundle.rulesets_path, path + ".field", repr(field))
            if not isinstance(reader_ref, str) or not reader_ref:
                c.e("SECTION_ENTITY_READER_INVALID", bundle.rulesets_path, path + ".reader", repr(reader_ref))
            elif not isinstance(node_ruleset.get(reader_ref), dict):
                c.e("SECTION_ENTITY_READER_UNRESOLVED", bundle.rulesets_path, path + ".reader", reader_ref)
            if "required" in reader and not isinstance(reader.get("required"), bool):
                c.e("SECTION_ENTITY_REQUIRED_INVALID", bundle.rulesets_path, path + ".required", repr(reader.get("required")))
        else:
            c.e("SECTION_READER_KIND_INVALID", bundle.rulesets_path, path + ".kind", str(kind))

    primitive_sets = dl(bundle.rulesets.get("logic_primitive_sets"))
    primitive_index = unique(primitive_sets, "id", c, bundle.rulesets_path, "$.logic_primitive_sets", "LOGIC_PRIMITIVE_SET")
    del primitive_index
    for set_index, primitive_set in enumerate(primitive_sets):
        seen_ops = set()
        for op_index, primitive in enumerate(dl(primitive_set.get("primitives"))):
            op = primitive.get("op")
            path = f"$.logic_primitive_sets[{set_index}].primitives[{op_index}].op"
            if not isinstance(op, str) or not op:
                c.e("LOGIC_OP_INVALID", bundle.rulesets_path, path, "non-empty required")
            elif op in seen_ops:
                c.e("LOGIC_OP_DUPLICATE", bundle.rulesets_path, path, op)
            else:
                seen_ops.add(op)

    contract_scope = bundle.rulesets.get("contract_scope")
    if isinstance(contract_scope, dict):
        affiliation = contract_scope.get("implementation_affiliation")
        if isinstance(affiliation, str) and affiliation not in link_index:
            c.e("CONTRACT_AFFILIATION_RULESET_UNRESOLVED", bundle.rulesets_path, "$.contract_scope.implementation_affiliation", affiliation)

    return c


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-set", type=Path)
    parser.add_argument("--ccf", type=Path)
    parser.add_argument("--nodetypes", type=Path)
    parser.add_argument("--rulesets", type=Path)
    parser.add_argument("--dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    args = parser.parse_args()
    try:
        bundle = resolve_bundle(
            spec_set=args.spec_set,
            ccf=args.ccf,
            nodetypes=args.nodetypes,
            rulesets=args.rulesets,
            spec_dir=args.dir,
            default_start=Path(__file__).parent,
        )
        findings = lint_bundle(bundle)
    except Exception as exc:
        print(json.dumps({"result": "IMPLEMENTATION_FAILURE", "message": str(exc)}) if args.json else f"cw_spec_lint: {exc}")
        return 2
    errors = sum(item.severity == "ERROR" for item in findings.f)
    if args.json:
        print(json.dumps({"linter_version": VER, "result": "INVALID_SPECIFICATION" if errors else "VALID_SPECIFICATION", "findings": [asdict(item) for item in findings.f]}, indent=2))
    else:
        print(f"CW spec lint v{VER}\nCCF {bundle.ccf.get('version')} / NodeTypes {bundle.nodetypes.get('version')} / Rulesets {bundle.rulesets.get('version')}")
        for item in findings.f:
            print(f"{item.severity} {item.code} {Path(item.file).name} {item.path}: {item.message}")
        print(f"\n{'FAIL' if errors else 'PASS'}: {errors} error(s)")
        if args.coverage:
            print("Coverage: specification-driven; NodeType inheritance, entity-field readers, generic topology selectors, Link endpoint constraints, flows and logic primitive closure validated")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
