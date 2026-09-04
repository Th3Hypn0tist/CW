#!/usr/bin/env python3
"""
CanonicalWireframe specification linter.

Scope
-----
This linter validates the public CW specification set itself:
- Canonical Contract Format (CCF)
- CW NodeTypes
- CW Dependency Rules / Rulesets

It does NOT claim to be the full canonical model/runtime validator described by
CCF.validator.required_operations. Its job is to prove that the specification
surface is internally coherent enough to be used by such a validator.

Default layout
--------------
    <repo>/
      Canonical_Contract_Format_v*.json
      CanonicalWireframe_NodeTypes_v*.json
      CanonicalWireframe_Dependency_Rules_v*.json
      linter/
        cw_spec_lint.py

Running from any current working directory scans the parent of this script by
default. Artifact discovery is content-based and version-independent.

Usage
-----
    python linter/cw_spec_lint.py
    python linter/cw_spec_lint.py --json
    python linter/cw_spec_lint.py --coverage
    python linter/cw_spec_lint.py --dir /path/to/specs

Exit codes
----------
    0 = no specification lint errors
    1 = specification lint errors found
    2 = operational failure
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

LINTER_VERSION = "1.0.0"

EXPECTED_IDS = {
    "ccf": "CANONICAL_CONTRACT_FORMAT",
    "nodetypes": "CW_NODETYPES",
    "rulesets": "CW_RULESETS",
}
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
RESULT_TOKEN_RE = re.compile(
    r"\b(?:INVALID_[A-Z][A-Z0-9_]*|IMPLEMENTATION_FAILURE|UNREADY|READY|CONFLICT)\b"
)
ALLOWED_CANONICAL_KINDS = {"Entity", "Property"}
ALLOWED_FLOW_DIRECTIONS = {"parent_ref_to_child_ref", "child_ref_to_parent_ref"}
ALLOWED_PRIMITIVE_CLASSES = {"statement", "expression"}

CORE_LOGIC_OPS = {
    "read", "write", "assign", "call", "return",
    "if", "while", "loop",
    "and", "or", "xor", "not",
    "eq", "ne", "lt", "lte", "gt", "gte",
}

# Exact current specification-integrity declarations that this linter
# mechanically covers. Exact matching is intentional: a new mandatory check in
# the spec must not become silently "implemented" by implication.
IMPLEMENTED_INTEGRITY_CHECKS = {
    "every NodeType extends id resolves and inheritance is acyclic",
    "every NodeType required/owned Property type resolves a Property Ruleset or canonical Link specialization",
    "every Required Link link_type_ref resolves exactly one Link Ruleset",
    "every Required Link self_role resolves in that Link Ruleset semantic_roles",
    "every Link Ruleset property_owner resolves one of its own semantic roles",
    "every unresolved_impact from_role/to_role resolves in that Link Ruleset semantic_roles",
    "every dependency_derivation used_role/consumer_role resolves in that Link Ruleset semantic_roles",
    "every flow pattern_ref resolves a declared flow pattern",
    "every flow NodeType case resolves a declared NodeType",
    "every endpoint constraint Entity NodeType resolves a declared NodeType",
    "every endpoint constraint Property type resolves a declared Property Ruleset",
    "every special same-Abstraction scope constraint is present on both source and consumer validation paths when required",
    "every top-level machine-significant mechanism referenced by prose has an explicit structured declaration",
    "every reference-bearing Property Ruleset declares reference_constraints for each canonical/external target-ref field",
    "every constrained allowed_nodetype_ref resolves a declared NodeType",
    "every Link endpoint uses the explicit default endpoint policy plus any narrower endpoint_constraints",
    "every reference-bearing Link Ruleset value field declares explicit reference_constraints or an explicit broad-by-design policy",
    "every function_call input_refs/output_refs target constraint resolves only canonical data Property semantics declared in the pinned specification closure",
    "every function_call flow pattern_ref resolves call_return",
    "every Function logic primitive_set_ref resolves exactly one Logic Primitive Set inside the pinned immutable specification closure",
    "every Logic Primitive Set op id is unique within that set and every primitive class/category/field contract is internally consistent",
    "every Function logic call_ref constraint targets canonical function_call Link Properties and preserves caller-function ownership semantics",
    "every Function logic canonical Data reference constraint resolves against declared Property Rulesets",
    "every machine-significant ordered logic body field explicitly declares ordered=true",
    "logic representation_ref/source projections are non-authoritative and no validator depends on parsing representation source to recover missing canonical semantics",
}


@dataclass
class Finding:
    severity: str
    code: str
    file: str
    path: str
    message: str


class DuplicateKeyError(ValueError):
    pass


class LintContext:
    def __init__(self) -> None:
        self.findings: List[Finding] = []

    def add(self, severity: str, code: str, file: Path | str, path: str, message: str) -> None:
        self.findings.append(Finding(severity, code, str(file), path or "$", message))

    def error(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("ERROR", code, file, path, message)

    def warn(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("WARNING", code, file, path, message)

    def info(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("INFO", code, file, path, message)


@dataclass
class Artifact:
    path: Path
    data: Dict[str, Any]
    kind: str

    @property
    def id(self) -> Optional[str]:
        value = self.data.get("id")
        return value if isinstance(value, str) and value else None

    @property
    def version(self) -> Optional[str]:
        value = self.data.get("version")
        return value if isinstance(value, str) and value else None


@dataclass
class Indexes:
    nodetypes: Dict[str, Dict[str, Any]]
    property_rulesets_by_id: Dict[str, Dict[str, Any]]
    link_rulesets_by_id: Dict[str, Dict[str, Any]]
    property_types: Dict[str, List[Dict[str, Any]]]
    link_types: Dict[str, List[Dict[str, Any]]]
    flow_patterns: Dict[str, Dict[str, Any]]
    logic_primitive_sets: Dict[str, Dict[str, Any]]


@dataclass
class Coverage:
    integrity_declared: List[str]
    integrity_implemented: List[str]
    integrity_unimplemented: List[str]
    validator_required_operations: List[str]
    validator_scope_note: str


def reject_duplicate_keys(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def load_json(path: Path, ctx: LintContext) -> Optional[Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        ctx.error("IO_READ_FAILED", path, "$", f"cannot read file: {exc}")
        return None

    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except DuplicateKeyError as exc:
        ctx.error("JSON_DUPLICATE_KEY", path, "$", str(exc))
    except json.JSONDecodeError as exc:
        ctx.error("JSON_PARSE_ERROR", path, "$", f"{exc.msg} at line {exc.lineno}, column {exc.colno}")
    except Exception as exc:
        ctx.error("JSON_PARSE_ERROR", path, "$", str(exc))
    return None


def classify(data: Any) -> str:
    if not isinstance(data, dict):
        return "other"
    if data.get("type") == "canonical_contract_format" or data.get("id") == "CANONICAL_CONTRACT_FORMAT":
        return "ccf"
    if data.get("id") == "CW_NODETYPES" or (
        isinstance(data.get("nodetypes"), list) and isinstance(data.get("nodetype_schema"), dict)
    ):
        return "nodetypes"
    if data.get("id") == "CW_RULESETS" or (
        isinstance(data.get("property_rulesets"), list) and isinstance(data.get("link_rulesets"), list)
    ):
        return "rulesets"
    return "other"


def discover(scan_dir: Path, ctx: LintContext) -> List[Artifact]:
    if not scan_dir.exists():
        ctx.error("SCAN_DIR_MISSING", scan_dir, "$", "scan directory does not exist")
        return []
    if not scan_dir.is_dir():
        ctx.error("SCAN_DIR_NOT_DIRECTORY", scan_dir, "$", "scan path is not a directory")
        return []

    artifacts: List[Artifact] = []
    for path in sorted(scan_dir.glob("*.json")):
        data = load_json(path, ctx)
        if isinstance(data, dict):
            artifacts.append(Artifact(path, data, classify(data)))
        elif data is not None:
            ctx.warn("JSON_ROOT_NOT_OBJECT", path, "$", "top-level JSON value is not an object")
    return artifacts


def one_or_error(items: Sequence[Artifact], kind: str, ctx: LintContext, scan_dir: Path) -> Optional[Artifact]:
    matches = [a for a in items if a.kind == kind]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        ctx.error(f"{kind.upper()}_NOT_FOUND", scan_dir, "$", f"could not discover a {kind} artifact from JSON content")
    else:
        ctx.error(
            f"{kind.upper()}_AMBIGUOUS",
            scan_dir,
            "$",
            "multiple candidate artifacts found: " + ", ".join(a.path.name for a in matches),
        )
    return None


def list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, dict)]


def string_list(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        return None
    return list(value)


def walk_strings(value: Any, path: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk_strings(child, f"{path}[{i}]")
    elif isinstance(value, str):
        yield path, value


def index_unique(
    items: Iterable[Dict[str, Any]],
    key: str,
    ctx: LintContext,
    file: Path,
    base_path: str,
    code_prefix: str,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for i, item in enumerate(items):
        value = item.get(key)
        path = f"{base_path}[{i}].{key}"
        if not isinstance(value, str) or not value:
            ctx.error(f"{code_prefix}_MISSING_ID", file, path, f"{key} must be a non-empty string")
            continue
        if value in out:
            ctx.error(f"{code_prefix}_DUPLICATE_ID", file, path, f"duplicate {key} {value!r}")
        else:
            out[value] = item
    return out


def check_min_max(obj: Any, ctx: LintContext, file: Path, path: str, code_prefix: str) -> None:
    if not isinstance(obj, dict):
        ctx.error(f"{code_prefix}_NOT_OBJECT", file, path, "cardinality constraint must be an object")
        return
    min_v, max_v = obj.get("min"), obj.get("max")
    for name, value in (("min", min_v), ("max", max_v)):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            ctx.error(
                f"{code_prefix}_BAD_{name.upper()}",
                file,
                f"{path}.{name}",
                f"{name} must be a non-negative integer when present",
            )
    if (
        isinstance(min_v, int) and not isinstance(min_v, bool)
        and isinstance(max_v, int) and not isinstance(max_v, bool)
        and min_v > max_v
    ):
        ctx.error(f"{code_prefix}_MIN_GT_MAX", file, path, f"min ({min_v}) exceeds max ({max_v})")


def parse_endpoint_constraint(value: str) -> Optional[Tuple[str, str]]:
    if ":" not in value:
        return None
    prefix, ref = value.split(":", 1)
    if prefix in {"entity_nodetype", "property"} and ref:
        return prefix, ref
    return None


def check_artifact_headers(artifacts: Sequence[Artifact], ctx: LintContext) -> None:
    required_by_kind = {
        "ccf": {"id", "name", "type", "version", "status", "purpose"},
        "nodetypes": {"id", "name", "version", "ccf_ref", "purpose", "nodetype_schema", "nodetypes"},
        "rulesets": {
            "id", "name", "version", "ccf_ref", "nodetypes_ref", "purpose",
            "principles", "property_rulesets", "link_rulesets",
        },
    }
    seen_ids: Dict[str, Path] = {}
    for art in artifacts:
        if art.kind == "other":
            continue
        expected_id = EXPECTED_IDS[art.kind]
        if art.id != expected_id:
            ctx.error("ARTIFACT_ID_MISMATCH", art.path, "$.id", f"{art.kind} id must be {expected_id!r}, got {art.id!r}")
        if art.id:
            if art.id in seen_ids:
                ctx.error("ARTIFACT_DUPLICATE_ID", art.path, "$.id", f"artifact id {art.id!r} also declared by {seen_ids[art.id].name}")
            seen_ids[art.id] = art.path
        if not isinstance(art.version, str) or not SEMVER_RE.match(art.version):
            ctx.error("ARTIFACT_VERSION_INVALID", art.path, "$.version", "version must be a semantic x.y.z string")
        for field in sorted(required_by_kind[art.kind]):
            if field not in art.data:
                ctx.error("ARTIFACT_REQUIRED_FIELD_MISSING", art.path, f"$.{field}", f"{art.kind} artifact is missing {field!r}")


def check_cross_refs(
    ccf: Artifact,
    nodetypes: Artifact,
    rulesets: Artifact,
    artifacts: Sequence[Artifact],
    ctx: LintContext,
) -> None:
    ids = {a.id for a in artifacts if a.id}

    def require_ref(art: Artifact, field: str, expected_id: Optional[str]) -> None:
        value = art.data.get(field)
        if not isinstance(value, str) or not value:
            ctx.error("CROSS_REF_MISSING", art.path, f"$.{field}", f"{field} must be a non-empty string")
            return
        if expected_id and value != expected_id:
            ctx.error("CROSS_REF_MISMATCH", art.path, f"$.{field}", f"{field}={value!r}, expected {expected_id!r}")
        elif value not in ids:
            ctx.error("CROSS_REF_UNRESOLVED", art.path, f"$.{field}", f"{field}={value!r} does not resolve in scanned core artifacts")

    require_ref(nodetypes, "ccf_ref", ccf.id)
    require_ref(rulesets, "ccf_ref", ccf.id)
    require_ref(rulesets, "nodetypes_ref", nodetypes.id)

    dep = ccf.data.get("dependency_rules")
    if not isinstance(dep, dict):
        ctx.error("CCF_DEPENDENCY_RULES_MISSING", ccf.path, "$.dependency_rules", "dependency_rules must be an object")
        return
    companion = dep.get("companion_ref")
    if not isinstance(companion, str) or companion != rulesets.id:
        ctx.error(
            "CCF_COMPANION_REF_MISMATCH",
            ccf.path,
            "$.dependency_rules.companion_ref",
            f"companion_ref must resolve the discovered Rulesets id {rulesets.id!r}",
        )


def build_indexes(nodetypes: Artifact, rulesets: Artifact, ctx: LintContext) -> Indexes:
    nt_items = list_of_dicts(nodetypes.data.get("nodetypes"))
    pr_items = list_of_dicts(rulesets.data.get("property_rulesets"))
    lr_items = list_of_dicts(rulesets.data.get("link_rulesets"))
    fp_items = list_of_dicts(rulesets.data.get("flow_patterns"))
    lp_items = list_of_dicts(rulesets.data.get("logic_primitive_sets"))

    nt_by_id = index_unique(nt_items, "id", ctx, nodetypes.path, "$.nodetypes", "NODETYPE")
    pr_by_id = index_unique(pr_items, "id", ctx, rulesets.path, "$.property_rulesets", "PROPERTY_RULESET")
    lr_by_id = index_unique(lr_items, "id", ctx, rulesets.path, "$.link_rulesets", "LINK_RULESET")
    fp_by_id = index_unique(fp_items, "id", ctx, rulesets.path, "$.flow_patterns", "FLOW_PATTERN")
    lp_by_id = index_unique(lp_items, "id", ctx, rulesets.path, "$.logic_primitive_sets", "LOGIC_PRIMITIVE_SET")

    property_types: Dict[str, List[Dict[str, Any]]] = {}
    for i, rule in enumerate(pr_items):
        ptype = rule.get("property_type_ref")
        if not isinstance(ptype, str) or not ptype:
            ctx.error("PROPERTY_RULESET_MISSING_PROPERTY_TYPE", rulesets.path, f"$.property_rulesets[{i}].property_type_ref", "property_type_ref must be non-empty")
            continue
        property_types.setdefault(ptype, []).append(rule)
    for ptype, matches in property_types.items():
        if len(matches) != 1:
            ctx.error("PROPERTY_TYPE_AMBIGUOUS", rulesets.path, "$.property_rulesets", f"property_type_ref {ptype!r} has {len(matches)} governing rulesets")

    link_types: Dict[str, List[Dict[str, Any]]] = {}
    for i, rule in enumerate(lr_items):
        if rule.get("property_type_ref") != "link":
            ctx.error("LINK_RULESET_PROPERTY_TYPE_NOT_LINK", rulesets.path, f"$.link_rulesets[{i}].property_type_ref", "every Link Ruleset must use property_type_ref='link'")
        ltype = rule.get("link_type_ref")
        if not isinstance(ltype, str) or not ltype:
            ctx.error("LINK_RULESET_MISSING_LINK_TYPE", rulesets.path, f"$.link_rulesets[{i}].link_type_ref", "link_type_ref must be non-empty")
            continue
        link_types.setdefault(ltype, []).append(rule)
    for ltype, matches in link_types.items():
        if len(matches) != 1:
            ctx.error("LINK_TYPE_AMBIGUOUS", rulesets.path, "$.link_rulesets", f"link_type_ref {ltype!r} has {len(matches)} governing rulesets")

    return Indexes(nt_by_id, pr_by_id, lr_by_id, property_types, link_types, fp_by_id, lp_by_id)


def check_nodetype_inheritance(nodetypes: Artifact, idx: Indexes, ctx: LintContext) -> None:
    graph: Dict[str, List[str]] = {}
    for i, nt in enumerate(list_of_dicts(nodetypes.data.get("nodetypes"))):
        nt_id = nt.get("id")
        if not isinstance(nt_id, str):
            continue
        parents = nt.get("extends", [])
        if parents is None:
            parents = []
        if not isinstance(parents, list):
            ctx.error("NODETYPE_EXTENDS_NOT_ARRAY", nodetypes.path, f"$.nodetypes[{i}].extends", "extends must be an array")
            graph[nt_id] = []
            continue
        valid: List[str] = []
        for j, parent in enumerate(parents):
            if not isinstance(parent, str) or parent not in idx.nodetypes:
                ctx.error("NODETYPE_EXTENDS_UNRESOLVED", nodetypes.path, f"$.nodetypes[{i}].extends[{j}]", f"unresolved NodeType {parent!r}")
            else:
                valid.append(parent)
        graph[nt_id] = valid

    visiting: Set[str] = set()
    visited: Set[str] = set()
    stack: List[str] = []

    def dfs(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            try:
                start = stack.index(node)
                cycle = stack[start:] + [node]
            except ValueError:
                cycle = [node, node]
            ctx.error("NODETYPE_INHERITANCE_CYCLE", nodetypes.path, "$.nodetypes", " -> ".join(cycle))
            return
        visiting.add(node)
        stack.append(node)
        for parent in graph.get(node, []):
            dfs(parent)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for nt_id in graph:
        dfs(nt_id)


def check_nodetype_properties_and_required_links(nodetypes: Artifact, idx: Indexes, ctx: LintContext) -> None:
    available_property_types = set(idx.property_types)
    for i, nt in enumerate(list_of_dicts(nodetypes.data.get("nodetypes"))):
        nt_id = nt.get("id", f"<index:{i}>")
        for field in ("required_property_types", "owned_property_types"):
            values = nt.get(field)
            if not isinstance(values, list):
                ctx.error("NODETYPE_PROPERTY_TYPES_NOT_ARRAY", nodetypes.path, f"$.nodetypes[{i}].{field}", f"{field} must be an array")
                continue
            for j, ptype in enumerate(values):
                resolved = isinstance(ptype, str) and (ptype in available_property_types or (ptype == "link" and bool(idx.link_types)))
                if not resolved:
                    ctx.error("NODETYPE_PROPERTY_TYPE_UNRESOLVED", nodetypes.path, f"$.nodetypes[{i}].{field}[{j}]", f"NodeType {nt_id!r} references unresolved property type {ptype!r}")

        cardinality = nt.get("property_cardinality")
        if cardinality is not None:
            if not isinstance(cardinality, dict):
                ctx.error("NODETYPE_CARDINALITY_NOT_OBJECT", nodetypes.path, f"$.nodetypes[{i}].property_cardinality", "property_cardinality must be an object")
            else:
                for ptype, limits in cardinality.items():
                    if ptype not in available_property_types and not (ptype == "link" and idx.link_types):
                        ctx.error("NODETYPE_CARDINALITY_PROPERTY_UNRESOLVED", nodetypes.path, f"$.nodetypes[{i}].property_cardinality.{ptype}", f"unresolved Property type {ptype!r}")
                    check_min_max(limits, ctx, nodetypes.path, f"$.nodetypes[{i}].property_cardinality.{ptype}", "NODETYPE_CARDINALITY")

        reqs = nt.get("required_links", [])
        if reqs is None:
            reqs = []
        if not isinstance(reqs, list):
            ctx.error("REQUIRED_LINKS_NOT_ARRAY", nodetypes.path, f"$.nodetypes[{i}].required_links", "required_links must be an array")
            continue
        seen: Set[str] = set()
        for j, req in enumerate(reqs):
            p = f"$.nodetypes[{i}].required_links[{j}]"
            if not isinstance(req, dict):
                ctx.error("REQUIRED_LINK_NOT_OBJECT", nodetypes.path, p, "Required Link must be an object")
                continue
            for field in ("id", "link_type_ref", "self_role", "min"):
                if field not in req:
                    ctx.error("REQUIRED_LINK_REQUIRED_FIELD_MISSING", nodetypes.path, f"{p}.{field}", f"missing {field!r}")
            req_id = req.get("id")
            if not isinstance(req_id, str) or not req_id:
                ctx.error("REQUIRED_LINK_ID_INVALID", nodetypes.path, f"{p}.id", "id must be a non-empty string")
            elif req_id in seen:
                ctx.error("REQUIRED_LINK_DUPLICATE_ID", nodetypes.path, f"{p}.id", f"duplicate Required Link id {req_id!r} in NodeType {nt_id!r}")
            else:
                seen.add(req_id)

            ltype = req.get("link_type_ref")
            matches = idx.link_types.get(ltype, []) if isinstance(ltype, str) else []
            if len(matches) != 1:
                ctx.error("REQUIRED_LINK_TYPE_UNRESOLVED_OR_AMBIGUOUS", nodetypes.path, f"{p}.link_type_ref", f"link_type_ref {ltype!r} resolves to {len(matches)} Link Rulesets")
            else:
                roles_obj = matches[0].get("semantic_roles")
                roles = set(roles_obj.values()) if isinstance(roles_obj, dict) else set()
                role = req.get("self_role")
                if not isinstance(role, str) or role not in roles:
                    ctx.error("REQUIRED_LINK_SELF_ROLE_UNRESOLVED", nodetypes.path, f"{p}.self_role", f"self_role {role!r} does not resolve in governing semantic_roles")
            check_min_max(req, ctx, nodetypes.path, p, "REQUIRED_LINK_CARDINALITY")

            other = req.get("other_endpoint")
            if other is not None:
                if not isinstance(other, dict):
                    ctx.error("REQUIRED_LINK_OTHER_ENDPOINT_NOT_OBJECT", nodetypes.path, f"{p}.other_endpoint", "other_endpoint must be an object")
                else:
                    nt_ref = other.get("entity_nodetype_ref")
                    if nt_ref is not None and (not isinstance(nt_ref, str) or nt_ref not in idx.nodetypes):
                        ctx.error("REQUIRED_LINK_OTHER_NODETYPE_UNRESOLVED", nodetypes.path, f"{p}.other_endpoint.entity_nodetype_ref", f"unresolved NodeType {nt_ref!r}")
                    pt_ref = other.get("property_type_ref")
                    if pt_ref is not None and not (
                        isinstance(pt_ref, str) and (pt_ref in idx.property_types or (pt_ref == "link" and idx.link_types))
                    ):
                        ctx.error("REQUIRED_LINK_OTHER_PROPERTY_UNRESOLVED", nodetypes.path, f"{p}.other_endpoint.property_type_ref", f"unresolved Property type {pt_ref!r}")


def check_schema_shape(schema: Any, file: Path, path: str, ctx: LintContext, code_prefix: str = "SCHEMA") -> None:
    if not isinstance(schema, dict):
        ctx.error(f"{code_prefix}_NOT_OBJECT", file, path, "schema must be an object")
        return
    required = schema.get("required", [])
    optional = schema.get("optional", [])
    fields = schema.get("fields")
    if not isinstance(required, list) or any(not isinstance(x, str) for x in required):
        ctx.error(f"{code_prefix}_REQUIRED_NOT_STRING_ARRAY", file, f"{path}.required", "required must be an array of strings")
        required = []
    if not isinstance(optional, list) or any(not isinstance(x, str) for x in optional):
        ctx.error(f"{code_prefix}_OPTIONAL_NOT_STRING_ARRAY", file, f"{path}.optional", "optional must be an array of strings")
        optional = []
    if not isinstance(fields, dict):
        ctx.error(f"{code_prefix}_FIELDS_NOT_OBJECT", file, f"{path}.fields", "fields must be an object")
        return
    req, opt = set(required), set(optional)
    overlap = sorted(req & opt)
    if overlap:
        ctx.error(f"{code_prefix}_REQUIRED_OPTIONAL_OVERLAP", file, path, f"fields both required and optional: {overlap}")
    missing = sorted((req | opt) - set(fields))
    if missing:
        ctx.error(f"{code_prefix}_DECLARED_FIELD_MISSING", file, f"{path}.fields", f"declared fields missing from fields: {missing}")
    semantic_unclassified = sorted(
        key for key, type_decl in fields.items()
        if key not in req | opt and isinstance(type_decl, str)
    )
    if semantic_unclassified:
        ctx.error(
            f"{code_prefix}_FIELD_NOT_CLASSIFIED",
            file,
            path,
            f"string-typed semantic fields must be required or optional: {semantic_unclassified}",
        )


def reference_bearing_fields(fields: Mapping[str, Any], skip: Set[str] | None = None) -> Set[str]:
    skip = skip or set()
    out: Set[str] = set()
    for field, type_decl in fields.items():
        if field in skip or not isinstance(type_decl, str):
            continue
        if "canonical_ref" in type_decl or "canonical_or_external_ref" in type_decl or type_decl == "external_ref":
            out.add(field)
    return out


def validate_reference_policy(
    policy: Any,
    rulesets: Artifact,
    path: str,
    idx: Indexes,
    ctx: LintContext,
) -> None:
    if not isinstance(policy, dict):
        ctx.error("REFERENCE_CONSTRAINT_NOT_OBJECT", rulesets.path, path, "reference constraint policy must be an object")
        return

    allowed_kinds = policy.get("allowed_canonical_kinds")
    if allowed_kinds is not None:
        if not isinstance(allowed_kinds, list) or any(x not in ALLOWED_CANONICAL_KINDS for x in allowed_kinds):
            ctx.error("REFERENCE_CONSTRAINT_BAD_CANONICAL_KIND", rulesets.path, f"{path}.allowed_canonical_kinds", "allowed_canonical_kinds must contain only Entity/Property")

    nts = policy.get("allowed_nodetype_refs")
    if nts is not None:
        if not isinstance(nts, list):
            ctx.error("ALLOWED_NODETYPES_NOT_ARRAY", rulesets.path, f"{path}.allowed_nodetype_refs", "must be an array")
        else:
            for i, ref in enumerate(nts):
                if not isinstance(ref, str) or ref not in idx.nodetypes:
                    ctx.error("REFERENCE_CONSTRAINT_NODETYPE_UNRESOLVED", rulesets.path, f"{path}.allowed_nodetype_refs[{i}]", f"unresolved NodeType {ref!r}")

    pts = policy.get("allowed_property_type_refs")
    if pts is not None:
        if not isinstance(pts, list):
            ctx.error("ALLOWED_PROPERTY_TYPES_NOT_ARRAY", rulesets.path, f"{path}.allowed_property_type_refs", "must be an array")
        else:
            for i, ref in enumerate(pts):
                if not isinstance(ref, str) or not (ref in idx.property_types or (ref == "link" and idx.link_types)):
                    ctx.error("REFERENCE_CONSTRAINT_PROPERTY_TYPE_UNRESOLVED", rulesets.path, f"{path}.allowed_property_type_refs[{i}]", f"unresolved Property type {ref!r}")

    ltype = policy.get("required_link_type_ref")
    if ltype is not None and (not isinstance(ltype, str) or len(idx.link_types.get(ltype, [])) != 1):
        ctx.error("REFERENCE_CONSTRAINT_LINK_TYPE_UNRESOLVED", rulesets.path, f"{path}.required_link_type_ref", f"required_link_type_ref {ltype!r} must resolve exactly one Link Ruleset")


def check_property_rulesets(rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    for i, rule in enumerate(list_of_dicts(rulesets.data.get("property_rulesets"))):
        p = f"$.property_rulesets[{i}]"
        check_schema_shape(rule.get("value_schema"), rulesets.path, f"{p}.value_schema", ctx, "VALUE_SCHEMA")
        schema = rule.get("value_schema")
        if not isinstance(schema, dict) or not isinstance(schema.get("fields"), dict):
            continue
        fields = schema["fields"]
        refs = reference_bearing_fields(fields)
        constraints = rule.get("reference_constraints")
        if refs and not isinstance(constraints, dict):
            ctx.error("REFERENCE_CONSTRAINT_POLICY_MISSING", rulesets.path, f"{p}.reference_constraints", f"reference-bearing fields require explicit policies: {sorted(refs)}")
            continue
        if isinstance(constraints, dict):
            for field in refs:
                if field not in constraints:
                    ctx.error("REFERENCE_CONSTRAINT_FIELD_MISSING", rulesets.path, f"{p}.reference_constraints.{field}", f"no explicit compatibility policy for {field!r}")
            for field, policy in constraints.items():
                cp = f"{p}.reference_constraints.{field}"
                if field not in fields:
                    ctx.error("REFERENCE_CONSTRAINT_UNKNOWN_FIELD", rulesets.path, cp, f"unknown value_schema field {field!r}")
                validate_reference_policy(policy, rulesets, cp, idx, ctx)


def check_flow_patterns(rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    for i, flow in enumerate(list_of_dicts(rulesets.data.get("flow_patterns"))):
        p = f"$.flow_patterns[{i}]"
        legs = flow.get("legs")
        if not isinstance(legs, list):
            ctx.error("FLOW_LEGS_NOT_ARRAY", rulesets.path, f"{p}.legs", "legs must be an array")
            continue
        phases: Set[str] = set()
        for j, leg in enumerate(legs):
            lp = f"{p}.legs[{j}]"
            if not isinstance(leg, dict):
                ctx.error("FLOW_LEG_NOT_OBJECT", rulesets.path, lp, "flow leg must be an object")
                continue
            phase = leg.get("phase")
            if not isinstance(phase, str) or not phase:
                ctx.error("FLOW_LEG_PHASE_INVALID", rulesets.path, f"{lp}.phase", "phase must be non-empty")
            elif phase in phases:
                ctx.error("FLOW_LEG_PHASE_DUPLICATE", rulesets.path, f"{lp}.phase", f"duplicate phase {phase!r}")
            else:
                phases.add(phase)
            direction = leg.get("direction")
            if direction not in ALLOWED_FLOW_DIRECTIONS:
                ctx.error("FLOW_LEG_DIRECTION_INVALID", rulesets.path, f"{lp}.direction", f"direction must be one of {sorted(ALLOWED_FLOW_DIRECTIONS)}")
            if "continuous" in leg and not isinstance(leg["continuous"], bool):
                ctx.error("FLOW_LEG_CONTINUOUS_INVALID", rulesets.path, f"{lp}.continuous", "continuous must be boolean")


def check_link_rulesets(rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    for i, rule in enumerate(list_of_dicts(rulesets.data.get("link_rulesets"))):
        p = f"$.link_rulesets[{i}]"
        check_schema_shape(rule.get("value_schema"), rulesets.path, f"{p}.value_schema", ctx, "VALUE_SCHEMA")
        schema = rule.get("value_schema")
        fields = schema.get("fields") if isinstance(schema, dict) else None
        if isinstance(fields, dict):
            # parent_ref/child_ref compatibility is governed by the explicit global
            # Link endpoint policy + endpoint_constraints.
            refs = reference_bearing_fields(fields, {"parent_ref", "child_ref"})
            constraints = rule.get("reference_constraints")
            if refs and not isinstance(constraints, dict):
                ctx.error("LINK_REFERENCE_CONSTRAINT_POLICY_MISSING", rulesets.path, f"{p}.reference_constraints", f"reference-bearing Link fields require explicit policies: {sorted(refs)}")
            if isinstance(constraints, dict):
                for field in refs:
                    if field not in constraints:
                        ctx.error("LINK_REFERENCE_CONSTRAINT_FIELD_MISSING", rulesets.path, f"{p}.reference_constraints.{field}", f"no explicit policy for {field!r}")
                for field, policy in constraints.items():
                    cp = f"{p}.reference_constraints.{field}"
                    if field not in fields:
                        ctx.error("LINK_REFERENCE_CONSTRAINT_UNKNOWN_FIELD", rulesets.path, cp, f"unknown value_schema field {field!r}")
                    validate_reference_policy(policy, rulesets, cp, idx, ctx)

        roles_obj = rule.get("semantic_roles")
        if not isinstance(roles_obj, dict) or not roles_obj:
            ctx.error("LINK_RULESET_SEMANTIC_ROLES_MISSING", rulesets.path, f"{p}.semantic_roles", "semantic_roles must be a non-empty object")
            roles: Set[str] = set()
        else:
            roles = {x for x in roles_obj.values() if isinstance(x, str)}
            for endpoint in ("parent_ref", "child_ref"):
                if endpoint not in roles_obj or not isinstance(roles_obj.get(endpoint), str):
                    ctx.error("LINK_RULESET_ENDPOINT_ROLES_INCOMPLETE", rulesets.path, f"{p}.semantic_roles.{endpoint}", f"{endpoint} semantic role is required")

        owner = rule.get("property_owner")
        if not isinstance(owner, str) or owner not in roles:
            ctx.error("LINK_RULESET_PROPERTY_OWNER_UNRESOLVED", rulesets.path, f"{p}.property_owner", f"property_owner {owner!r} must resolve one semantic role")

        impact = rule.get("unresolved_impact")
        if impact is not None:
            if not isinstance(impact, dict):
                ctx.error("UNRESOLVED_IMPACT_NOT_OBJECT", rulesets.path, f"{p}.unresolved_impact", "must be an object")
            else:
                for field in ("from_role", "to_role"):
                    value = impact.get(field)
                    if not isinstance(value, str) or value not in roles:
                        ctx.error("UNRESOLVED_IMPACT_ROLE_UNRESOLVED", rulesets.path, f"{p}.unresolved_impact.{field}", f"{field} {value!r} does not resolve a semantic role")

        deriv = rule.get("dependency_derivation")
        if deriv is not None:
            if not isinstance(deriv, dict):
                ctx.error("DEPENDENCY_DERIVATION_NOT_OBJECT", rulesets.path, f"{p}.dependency_derivation", "must be an object")
            elif deriv.get("dependency_forming") is True:
                for field in ("used_role", "consumer_role"):
                    value = deriv.get(field)
                    if not isinstance(value, str) or value not in roles:
                        ctx.error("DEPENDENCY_DERIVATION_ROLE_UNRESOLVED", rulesets.path, f"{p}.dependency_derivation.{field}", f"{field} {value!r} does not resolve a semantic role")

        flow = rule.get("flow")
        if flow is not None:
            if not isinstance(flow, dict):
                ctx.error("FLOW_NOT_OBJECT", rulesets.path, f"{p}.flow", "flow must be an object")
            else:
                direct = flow.get("pattern_ref")
                if direct is not None and (not isinstance(direct, str) or direct not in idx.flow_patterns):
                    ctx.error("FLOW_PATTERN_UNRESOLVED", rulesets.path, f"{p}.flow.pattern_ref", f"unresolved flow pattern {direct!r}")
                cases = flow.get("cases")
                if cases is not None:
                    if not isinstance(cases, list):
                        ctx.error("FLOW_CASES_NOT_ARRAY", rulesets.path, f"{p}.flow.cases", "cases must be an array")
                    else:
                        for j, case in enumerate(cases):
                            cp = f"{p}.flow.cases[{j}]"
                            if not isinstance(case, dict):
                                ctx.error("FLOW_CASE_NOT_OBJECT", rulesets.path, cp, "flow case must be an object")
                                continue
                            nt_ref = case.get("parent_owner_nodetype_ref")
                            if not isinstance(nt_ref, str) or nt_ref not in idx.nodetypes:
                                ctx.error("FLOW_CASE_NODETYPE_UNRESOLVED", rulesets.path, f"{cp}.parent_owner_nodetype_ref", f"unresolved NodeType {nt_ref!r}")
                            pattern = case.get("pattern_ref")
                            if not isinstance(pattern, str) or pattern not in idx.flow_patterns:
                                ctx.error("FLOW_CASE_PATTERN_UNRESOLVED", rulesets.path, f"{cp}.pattern_ref", f"unresolved flow pattern {pattern!r}")
                excluded = flow.get("excluded_nodetype_refs")
                if isinstance(excluded, dict):
                    for nt_ref in excluded:
                        if nt_ref not in idx.nodetypes:
                            ctx.error("FLOW_EXCLUDED_NODETYPE_UNRESOLVED", rulesets.path, f"{p}.flow.excluded_nodetype_refs.{nt_ref}", f"unresolved NodeType {nt_ref!r}")

        epc = rule.get("endpoint_constraints")
        if epc is not None:
            if not isinstance(epc, dict):
                ctx.error("ENDPOINT_CONSTRAINTS_NOT_OBJECT", rulesets.path, f"{p}.endpoint_constraints", "must be an object")
            else:
                for endpoint, constraints in epc.items():
                    ep = f"{p}.endpoint_constraints.{endpoint}"
                    if endpoint not in {"parent_ref", "child_ref"}:
                        ctx.error("ENDPOINT_CONSTRAINT_UNKNOWN_ENDPOINT", rulesets.path, ep, f"unknown endpoint {endpoint!r}")
                    if not isinstance(constraints, list):
                        ctx.error("ENDPOINT_CONSTRAINT_NOT_ARRAY", rulesets.path, ep, "endpoint constraint must be an array")
                        continue
                    for j, constraint in enumerate(constraints):
                        cp = f"{ep}[{j}]"
                        if not isinstance(constraint, str):
                            ctx.error("ENDPOINT_CONSTRAINT_NOT_STRING", rulesets.path, cp, "constraint must be a string")
                            continue
                        parsed = parse_endpoint_constraint(constraint)
                        if parsed is None:
                            ctx.error("ENDPOINT_CONSTRAINT_UNKNOWN_SYNTAX", rulesets.path, cp, f"unsupported syntax {constraint!r}")
                            continue
                        kind, ref = parsed
                        if kind == "entity_nodetype" and ref not in idx.nodetypes:
                            ctx.error("ENDPOINT_NODETYPE_UNRESOLVED", rulesets.path, cp, f"unresolved NodeType {ref!r}")
                        if kind == "property" and not (ref in idx.property_types or (ref == "link" and idx.link_types)):
                            ctx.error("ENDPOINT_PROPERTY_TYPE_UNRESOLVED", rulesets.path, cp, f"unresolved Property type {ref!r}")


def check_shared_value_types(rulesets: Artifact, ctx: LintContext) -> None:
    shared = rulesets.data.get("shared_value_types")
    if not isinstance(shared, dict):
        return
    for name, schema in shared.items():
        if not isinstance(schema, dict):
            ctx.error("SHARED_VALUE_TYPE_NOT_OBJECT", rulesets.path, f"$.shared_value_types.{name}", "shared value type must be an object")
            continue
        if "required" in schema or "optional" in schema or "fields" in schema:
            check_schema_shape(schema, rulesets.path, f"$.shared_value_types.{name}", ctx, "SHARED_VALUE_SCHEMA")

    # Function.logic's shared named value type and the explicit RULESET_FUNCTION
    # logic_schema must describe the same canonical shape. This catches stale
    # pre-primitive function_logic definitions.
    shared_logic = shared.get("function_logic")
    function_rules = [r for r in list_of_dicts(rulesets.data.get("property_rulesets")) if r.get("property_type_ref") == "function"]
    if isinstance(shared_logic, dict) and len(function_rules) == 1:
        logic_schema = function_rules[0].get("logic_schema")
        if isinstance(logic_schema, dict):
            for field in ("required", "optional", "fields"):
                if shared_logic.get(field) != logic_schema.get(field):
                    ctx.error(
                        "FUNCTION_LOGIC_SHARED_SCHEMA_MISMATCH",
                        rulesets.path,
                        f"$.shared_value_types.function_logic.{field}",
                        f"shared function_logic {field} must match RULESET_FUNCTION.logic_schema.{field}",
                    )


def check_logic_primitive_sets(rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    for set_index, primitive_set in enumerate(list_of_dicts(rulesets.data.get("logic_primitive_sets"))):
        p = f"$.logic_primitive_sets[{set_index}]"
        set_id = primitive_set.get("id")
        primitives = primitive_set.get("primitives")
        if not isinstance(primitives, list):
            ctx.error("LOGIC_PRIMITIVES_NOT_ARRAY", rulesets.path, f"{p}.primitives", "primitives must be an array")
            continue
        ops: Dict[str, Dict[str, Any]] = {}
        for i, primitive in enumerate(primitives):
            pp = f"{p}.primitives[{i}]"
            if not isinstance(primitive, dict):
                ctx.error("LOGIC_PRIMITIVE_NOT_OBJECT", rulesets.path, pp, "primitive must be an object")
                continue
            op = primitive.get("op")
            if not isinstance(op, str) or not op:
                ctx.error("LOGIC_PRIMITIVE_OP_INVALID", rulesets.path, f"{pp}.op", "op must be non-empty")
                continue
            if op in ops:
                ctx.error("LOGIC_PRIMITIVE_DUPLICATE_OP", rulesets.path, f"{pp}.op", f"duplicate op {op!r} in primitive set {set_id!r}")
            else:
                ops[op] = primitive

            cls = primitive.get("class")
            if cls not in ALLOWED_PRIMITIVE_CLASSES:
                ctx.error("LOGIC_PRIMITIVE_CLASS_INVALID", rulesets.path, f"{pp}.class", f"class must be one of {sorted(ALLOWED_PRIMITIVE_CLASSES)}")
            category = primitive.get("category")
            if not isinstance(category, str) or not category:
                ctx.error("LOGIC_PRIMITIVE_CATEGORY_INVALID", rulesets.path, f"{pp}.category", "category must be non-empty")
            if not isinstance(primitive.get("semantics"), str) or not primitive["semantics"]:
                ctx.error("LOGIC_PRIMITIVE_SEMANTICS_MISSING", rulesets.path, f"{pp}.semantics", "semantics must be non-empty")

            required = primitive.get("required")
            optional = primitive.get("optional")
            fields = primitive.get("fields")
            if not isinstance(required, list) or any(not isinstance(x, str) for x in required):
                ctx.error("LOGIC_PRIMITIVE_REQUIRED_INVALID", rulesets.path, f"{pp}.required", "required must be a string array")
                required = []
            if "op" not in required:
                ctx.error("LOGIC_PRIMITIVE_OP_NOT_REQUIRED", rulesets.path, f"{pp}.required", "op must be required")
            if not isinstance(optional, list) or any(not isinstance(x, str) for x in optional):
                ctx.error("LOGIC_PRIMITIVE_OPTIONAL_INVALID", rulesets.path, f"{pp}.optional", "optional must be a string array")
                optional = []
            if set(required) & set(optional):
                ctx.error("LOGIC_PRIMITIVE_REQUIRED_OPTIONAL_OVERLAP", rulesets.path, pp, "required and optional must not overlap")
            if not isinstance(fields, dict):
                ctx.error("LOGIC_PRIMITIVE_FIELDS_INVALID", rulesets.path, f"{pp}.fields", "fields must be an object")
                fields = {}
            for field in set(required) | set(optional):
                if field != "op" and field not in fields:
                    ctx.error("LOGIC_PRIMITIVE_FIELD_MISSING", rulesets.path, f"{pp}.fields.{field}", f"declared field {field!r} missing from fields")
            # String-valued field declarations are semantic value fields and
            # must be classified. Numeric metadata such as min_args is allowed.
            for field, type_decl in fields.items():
                if isinstance(type_decl, str) and field not in set(required) | set(optional):
                    ctx.error("LOGIC_PRIMITIVE_FIELD_UNCLASSIFIED", rulesets.path, f"{pp}.fields.{field}", f"semantic field {field!r} must be required or optional")

            ordered = primitive.get("ordered")
            if ordered is not None:
                if not isinstance(ordered, dict):
                    ctx.error("LOGIC_PRIMITIVE_ORDERED_INVALID", rulesets.path, f"{pp}.ordered", "ordered must be an object")
                else:
                    for field, flag in ordered.items():
                        if field not in fields:
                            ctx.error("LOGIC_PRIMITIVE_ORDERED_UNKNOWN_FIELD", rulesets.path, f"{pp}.ordered.{field}", f"unknown field {field!r}")
                        if flag is not True:
                            ctx.error("LOGIC_PRIMITIVE_ORDERED_NOT_TRUE", rulesets.path, f"{pp}.ordered.{field}", "machine-significant ordered body field must declare true")

            rc = primitive.get("reference_constraints")
            if isinstance(rc, dict):
                for key, policy in rc.items():
                    validate_reference_policy(policy, rulesets, f"{pp}.reference_constraints.{key}", idx, ctx)

        if set_id == "CW_LOGIC_PRIMITIVES":
            missing = sorted(CORE_LOGIC_OPS - set(ops))
            if missing:
                ctx.error("CW_LOGIC_CORE_OPS_MISSING", rulesets.path, f"{p}.primitives", f"missing canonical logic ops: {missing}")

        ordered_fields = primitive_set.get("ordered_fields")
        if not isinstance(ordered_fields, list):
            ctx.error("LOGIC_ORDERED_FIELDS_INVALID", rulesets.path, f"{p}.ordered_fields", "ordered_fields must be an array")
            ordered_fields = []
        function_rule = next((r for r in list_of_dicts(rulesets.data.get("property_rulesets")) if r.get("property_type_ref") == "function"), None)
        logic_schema = function_rule.get("logic_schema") if isinstance(function_rule, dict) else None
        for j, entry in enumerate(ordered_fields):
            ep = f"{p}.ordered_fields[{j}]"
            if entry == "Function.logic.body":
                if not isinstance(logic_schema, dict) or not isinstance(logic_schema.get("ordered"), dict) or logic_schema["ordered"].get("body") is not True:
                    ctx.error("FUNCTION_LOGIC_BODY_ORDER_NOT_DECLARED", rulesets.path, ep, "Function.logic.body requires RULESET_FUNCTION.logic_schema.ordered.body=true")
                continue
            if not isinstance(entry, str) or "." not in entry:
                ctx.error("LOGIC_ORDERED_FIELD_INVALID", rulesets.path, ep, f"invalid ordered field reference {entry!r}")
                continue
            op, field = entry.split(".", 1)
            primitive = ops.get(op)
            if not isinstance(primitive, dict):
                ctx.error("LOGIC_ORDERED_FIELD_OP_UNRESOLVED", rulesets.path, ep, f"ordered field op {op!r} does not resolve")
                continue
            ordered = primitive.get("ordered")
            if not isinstance(ordered, dict) or ordered.get(field) is not True:
                ctx.error("LOGIC_ORDERED_FIELD_NOT_DECLARED", rulesets.path, ep, f"{entry} requires primitive ordered.{field}=true")

        for op in ("and", "or", "xor"):
            primitive = ops.get(op)
            if isinstance(primitive, dict) and primitive.get("args_ordered") is not False:
                ctx.error("LOGIC_BOOLEAN_ARGS_ORDER_INVALID", rulesets.path, p, f"{op}.args_ordered must be false")
        for op in ("eq", "ne", "lt", "lte", "gt", "gte"):
            primitive = ops.get(op)
            fields = primitive.get("fields") if isinstance(primitive, dict) else None
            if not isinstance(fields, dict) or "left" not in fields or "right" not in fields:
                ctx.error("LOGIC_COMPARISON_DIRECTION_FIELDS_MISSING", rulesets.path, p, f"{op} must declare explicit left/right fields")


def get_single_link_rule(idx: Indexes, link_type: str) -> Optional[Dict[str, Any]]:
    matches = idx.link_types.get(link_type, [])
    return matches[0] if len(matches) == 1 else None


def constraints_equal(rule: Mapping[str, Any], endpoint: str, expected: Set[str]) -> bool:
    epc = rule.get("endpoint_constraints")
    values = epc.get(endpoint) if isinstance(epc, dict) else None
    return isinstance(values, list) and set(values) == expected


def check_special_contracts(ccf: Artifact, nodetypes: Artifact, rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    function_call = get_single_link_rule(idx, "function_call")
    if not function_call:
        ctx.error("FUNCTION_CALL_RULESET_MISSING", rulesets.path, "$.link_rulesets", "function_call must resolve exactly one Link Ruleset")
    else:
        if function_call.get("flow", {}).get("pattern_ref") != "call_return":
            ctx.error("FUNCTION_CALL_FLOW_INVALID", rulesets.path, "$.link_rulesets", "function_call must use call_return")
        if not constraints_equal(function_call, "parent_ref", {"property:function"}) or not constraints_equal(function_call, "child_ref", {"property:function"}):
            ctx.error("FUNCTION_CALL_ENDPOINTS_INVALID", rulesets.path, "$.link_rulesets", "function_call endpoints must both be property:function")
        roles = function_call.get("semantic_roles")
        if roles != {"parent_ref": "caller_function", "child_ref": "called_function"}:
            ctx.error("FUNCTION_CALL_ROLES_INVALID", rulesets.path, "$.link_rulesets", "function_call roles must be caller_function -> called_function")
        if function_call.get("property_owner") != "caller_function":
            ctx.error("FUNCTION_CALL_OWNER_INVALID", rulesets.path, "$.link_rulesets", "function_call property_owner must be caller_function")
        rc = function_call.get("reference_constraints")
        for side in ("input_refs", "output_refs"):
            policy = rc.get(side) if isinstance(rc, dict) else None
            if not isinstance(policy, dict) or policy.get("allowed_canonical_kinds") != ["Property"] or policy.get("allowed_property_type_refs") != ["data"]:
                ctx.error("FUNCTION_CALL_DATA_REF_CONSTRAINT_INVALID", rulesets.path, f"$.link_rulesets[function_call].reference_constraints.{side}", f"{side} must resolve only canonical data Properties")

    event_handler = get_single_link_rule(idx, "event_handler")
    if not event_handler or not constraints_equal(event_handler, "parent_ref", {"property:event"}) or not constraints_equal(event_handler, "child_ref", {"property:function"}):
        ctx.error("EVENT_HANDLER_CONTRACT_INVALID", rulesets.path, "$.link_rulesets", "event_handler must be event Property -> function Property")

    binding_consume = get_single_link_rule(idx, "binding_consume")
    if not binding_consume or not constraints_equal(binding_consume, "parent_ref", {"entity_nodetype:binding"}) or not constraints_equal(binding_consume, "child_ref", {"entity_nodetype:output"}):
        ctx.error("BINDING_CONSUME_CONTRACT_INVALID", rulesets.path, "$.link_rulesets", "binding_consume must be binding Entity -> output Entity")

    boundary_output = get_single_link_rule(idx, "boundary_output")
    if not boundary_output or not constraints_equal(boundary_output, "child_ref", {"entity_nodetype:output"}):
        ctx.error("BOUNDARY_OUTPUT_CONTRACT_INVALID", rulesets.path, "$.link_rulesets", "boundary_output child_ref must be output Entity")

    # CCF vocabulary must resolve against the companion ruleset vocabulary.
    event_model = ccf.data.get("event_model")
    refs = event_model.get("canonical_reference_links") if isinstance(event_model, dict) else None
    if isinstance(refs, list):
        for i, ref in enumerate(refs):
            if not isinstance(ref, str) or len(idx.link_types.get(ref, [])) != 1:
                ctx.error("CCF_EVENT_LINK_TYPE_UNRESOLVED", ccf.path, f"$.event_model.canonical_reference_links[{i}]", f"unresolved event Link type {ref!r}")
    if len(idx.link_types.get("effect_target", [])) != 1:
        ctx.error("CCF_EFFECT_TARGET_UNRESOLVED", ccf.path, "$.effect_model", "effect_target Link specialization must resolve exactly once")

    # NodeTypes mirrors.
    api_contract = nodetypes.data.get("api_io_contract")
    api_rules = idx.property_types.get("api", [])
    if isinstance(api_contract, dict) and len(api_rules) == 1:
        rc = api_rules[0].get("reference_constraints")
        if isinstance(rc, dict):
            for side in ("input_refs", "output_refs"):
                nt_side = api_contract.get(side)
                rs_side = rc.get(side)
                if isinstance(nt_side, dict) and isinstance(rs_side, dict):
                    if set(nt_side.get("allowed_nodetype_refs", [])) != set(rs_side.get("allowed_nodetype_refs", [])):
                        ctx.error("API_IO_NODETYPE_MIRROR_MISMATCH", nodetypes.path, f"$.api_io_contract.{side}.allowed_nodetype_refs", "NodeTypes and RULESET_API allowed NodeTypes differ")
                    if nt_side.get("nodetype_matching") != rs_side.get("nodetype_matching"):
                        ctx.error("API_IO_MATCH_POLICY_MISMATCH", nodetypes.path, f"$.api_io_contract.{side}.nodetype_matching", "NodeTypes and RULESET_API matching policy differ")


def check_structured_scope_mechanisms(nodetypes: Artifact, rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    binding = rulesets.data.get("binding")
    if not isinstance(binding, dict):
        ctx.error("BINDING_STRUCTURED_MECHANISM_MISSING", rulesets.path, "$.binding", "Binding scope/typing mechanism must have a structured declaration")
    else:
        scope = binding.get("scope")
        if not isinstance(scope, dict) or scope.get("same_abstraction_only") is not True or scope.get("cross_abstraction_lookup") is not False or scope.get("cross_abstraction_consumption") is not False:
            ctx.error("BINDING_SCOPE_DECLARATION_INVALID", rulesets.path, "$.binding.scope", "Binding must structurally declare same-Abstraction-only lookup/consumption")
        inp = binding.get("input")
        if not isinstance(inp, dict) or inp.get("scope") != "same_abstraction_only" or inp.get("source_endpoint_scope") != "same_abstraction_only":
            ctx.error("BINDING_SOURCE_SCOPE_DECLARATION_INVALID", rulesets.path, "$.binding.input", "Binding source and source endpoint must be same-Abstraction-only")
        out = binding.get("output_consumption")
        if not isinstance(out, dict) or out.get("same_abstraction_only") is not True or out.get("link_type_ref") != "binding_consume":
            ctx.error("BINDING_CONSUMER_SCOPE_DECLARATION_INVALID", rulesets.path, "$.binding.output_consumption", "Binding consumer path must structurally declare binding_consume + same-Abstraction-only")

    output = rulesets.data.get("output_source_resolution")
    if not isinstance(output, dict):
        ctx.error("OUTPUT_SOURCE_STRUCTURED_MECHANISM_MISSING", rulesets.path, "$.output_source_resolution", "Output source resolution must be structured")
    else:
        if output.get("scope") != "same_abstraction_only":
            ctx.error("OUTPUT_SOURCE_SCOPE_INVALID", rulesets.path, "$.output_source_resolution.scope", "Output source scope must be same_abstraction_only")
        allowed = output.get("allowed_source_link_types")
        if not isinstance(allowed, list) or set(allowed) != {"boundary_output", "binding_consume"}:
            ctx.error("OUTPUT_SOURCE_LINK_TYPES_INVALID", rulesets.path, "$.output_source_resolution.allowed_source_link_types", "Output sources must be exactly boundary_output or binding_consume")
        card = output.get("cardinality_across_allowed_source_types")
        if not isinstance(card, dict) or card.get("min") != 1 or card.get("max") != 1:
            ctx.error("OUTPUT_SOURCE_CARDINALITY_INVALID", rulesets.path, "$.output_source_resolution.cardinality_across_allowed_source_types", "Output source cardinality must be exactly one")

    nt_binding = nodetypes.data.get("binding_model")
    if not isinstance(nt_binding, dict) or nt_binding.get("scope") != "same_abstraction_only" or nt_binding.get("source_scope") != "same_abstraction_only" or nt_binding.get("source_endpoint_scope") != "same_abstraction_only":
        ctx.error("NODETYPE_BINDING_SCOPE_MIRROR_INVALID", nodetypes.path, "$.binding_model", "NodeTypes binding model must mirror same-Abstraction source/consumer scope")


def check_link_default_policy(rulesets: Artifact, ctx: LintContext) -> None:
    obj = rulesets.data.get("link_reference_compatibility")
    default = obj.get("default_endpoint_policy") if isinstance(obj, dict) else None
    if not isinstance(default, dict):
        ctx.error("LINK_DEFAULT_ENDPOINT_POLICY_MISSING", rulesets.path, "$.link_reference_compatibility.default_endpoint_policy", "explicit default Link endpoint policy is required")
        return
    if default.get("allowed_reference_class") != "canonical_identity_ref":
        ctx.error("LINK_DEFAULT_REFERENCE_CLASS_INVALID", rulesets.path, "$.link_reference_compatibility.default_endpoint_policy.allowed_reference_class", "Link endpoints must use canonical_identity_ref")
    kinds = default.get("allowed_canonical_kinds")
    if not isinstance(kinds, list) or set(kinds) != {"Entity", "Property"}:
        ctx.error("LINK_DEFAULT_CANONICAL_KINDS_INVALID", rulesets.path, "$.link_reference_compatibility.default_endpoint_policy.allowed_canonical_kinds", "default Link endpoint kinds must be Entity + Property")
    if default.get("policy") != "broad_by_design_unless_narrowed":
        ctx.error("LINK_DEFAULT_POLICY_INVALID", rulesets.path, "$.link_reference_compatibility.default_endpoint_policy.policy", "default Link policy must be broad_by_design_unless_narrowed")


def check_function_logic_contract(rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    functions = idx.property_types.get("function", [])
    if len(functions) != 1:
        return
    rule = functions[0]
    schema = rule.get("logic_schema")
    if not isinstance(schema, dict):
        ctx.error("FUNCTION_LOGIC_SCHEMA_MISSING", rulesets.path, "$.property_rulesets[RULESET_FUNCTION].logic_schema", "logic_schema is required")
        return
    check_schema_shape(schema, rulesets.path, "$.property_rulesets[RULESET_FUNCTION].logic_schema", ctx, "FUNCTION_LOGIC_SCHEMA")
    fields = schema.get("fields")
    if not isinstance(fields, dict) or fields.get("primitive_set_ref") != "local_logic_primitive_set_ref" or fields.get("body") != "array<logic_statement>":
        ctx.error("FUNCTION_LOGIC_SCHEMA_FIELDS_INVALID", rulesets.path, "$.property_rulesets[RULESET_FUNCTION].logic_schema.fields", "logic must declare primitive_set_ref + ordered body")
    if not isinstance(schema.get("ordered"), dict) or schema["ordered"].get("body") is not True:
        ctx.error("FUNCTION_LOGIC_BODY_ORDER_NOT_DECLARED", rulesets.path, "$.property_rulesets[RULESET_FUNCTION].logic_schema.ordered.body", "body must declare ordered=true")

    semantics = rule.get("logic_semantics")
    if not isinstance(semantics, dict):
        ctx.error("FUNCTION_LOGIC_SEMANTICS_MISSING", rulesets.path, "$.property_rulesets[RULESET_FUNCTION].logic_semantics", "structured logic authority boundary is required")
    else:
        expected_false = (
            "representations_are_canonical_authority",
            "parse_representation_to_invent_missing_semantics",
            "runtime_execution_claim",
            "implementation_correspondence_claim",
        )
        for field in expected_false:
            if semantics.get(field) is not False:
                ctx.error("FUNCTION_LOGIC_AUTHORITY_BOUNDARY_INVALID", rulesets.path, f"$.property_rulesets[RULESET_FUNCTION].logic_semantics.{field}", f"{field} must be false")

    oracle = rulesets.data.get("function_logic_test_oracle")
    example = oracle.get("example") if isinstance(oracle, dict) else None
    normalized = example.get("normalized_logic") if isinstance(example, dict) else None
    ref = normalized.get("primitive_set_ref") if isinstance(normalized, dict) else None
    if not isinstance(ref, str) or ref not in idx.logic_primitive_sets:
        ctx.error("FUNCTION_LOGIC_ORACLE_PRIMITIVE_SET_UNRESOLVED", rulesets.path, "$.function_logic_test_oracle.example.normalized_logic.primitive_set_ref", f"primitive_set_ref {ref!r} must resolve")


def declared_result_classes(rulesets: Artifact) -> Set[str]:
    model = rulesets.data.get("evaluation_result_model")
    classes = model.get("classes") if isinstance(model, dict) else None
    return set(classes) if isinstance(classes, dict) else set()


def check_result_taxonomy(ccf: Artifact, nodetypes: Artifact, rulesets: Artifact, ctx: LintContext) -> None:
    declared = declared_result_classes(rulesets)
    if not declared:
        ctx.error("RESULT_TAXONOMY_MISSING", rulesets.path, "$.evaluation_result_model.classes", "overall evaluation taxonomy is missing")
        return

    for art in (ccf, nodetypes, rulesets):
        for path, text in walk_strings(art.data):
            for token in RESULT_TOKEN_RE.findall(text):
                if token not in declared and token not in {"READY", "UNREADY"}:
                    ctx.error("UNDECLARED_RESULT_CLASS", art.path, path, f"result-like token {token!r} is not in overall taxonomy {sorted(declared)}")

    validator = ccf.data.get("validator")
    states = validator.get("finding_states") if isinstance(validator, dict) else None
    model = rulesets.data.get("evaluation_result_model")
    recon = model.get("finding_state_reconciliation") if isinstance(model, dict) else None
    mapping = recon.get("mapping") if isinstance(recon, dict) else None
    if not isinstance(states, list) or not all(isinstance(x, str) for x in states):
        ctx.error("CCF_FINDING_STATES_INVALID", ccf.path, "$.validator.finding_states", "finding_states must be a string array")
        return
    if not isinstance(mapping, dict):
        ctx.error("FINDING_STATE_RECONCILIATION_MISSING", rulesets.path, "$.evaluation_result_model.finding_state_reconciliation.mapping", "every CCF finding state must be reconciled")
        return
    missing = sorted(set(states) - set(mapping))
    extra = sorted(set(mapping) - set(states))
    if missing:
        ctx.error("FINDING_STATE_RECONCILIATION_INCOMPLETE", rulesets.path, "$.evaluation_result_model.finding_state_reconciliation.mapping", f"missing mappings: {missing}")
    if extra:
        ctx.error("FINDING_STATE_RECONCILIATION_UNKNOWN_STATE", rulesets.path, "$.evaluation_result_model.finding_state_reconciliation.mapping", f"unknown mapped states: {extra}")
    expected = {
        "unready": "UNREADY",
        "ready": "READY",
        "conflict": "CONFLICT",
        "invalid_specification": "INVALID_SPECIFICATION",
        "invalid_model": "INVALID_MODEL",
        "implementation_failure": "IMPLEMENTATION_FAILURE",
    }
    for state, cls in expected.items():
        if state in mapping:
            value = mapping[state]
            if not isinstance(value, str) or cls not in value:
                ctx.error("FINDING_STATE_RECONCILIATION_BAD_TARGET", rulesets.path, f"$.evaluation_result_model.finding_state_reconciliation.mapping.{state}", f"{state} must map to {cls}")


def check_immutable_resolution_declarations(ccf: Artifact, rulesets: Artifact, ctx: LintContext) -> None:
    ccf_spec = ccf.data.get("contract_shape", {}).get("specification_ref") if isinstance(ccf.data.get("contract_shape"), dict) else None
    if not isinstance(ccf_spec, dict) or ccf_spec.get("required") is not True:
        ctx.error("CCF_SPECIFICATION_REF_CONTRACT_INVALID", ccf.path, "$.contract_shape.specification_ref", "specification_ref must be explicitly required")

    closure = rulesets.data.get("evaluation_dependency_closure")
    if not isinstance(closure, dict) or closure.get("same_root_same_closure") is not True:
        ctx.error("TRANSITIVE_CLOSURE_IMMUTABILITY_DECLARATION_MISSING", rulesets.path, "$.evaluation_dependency_closure.same_root_same_closure", "same specification root must imply same transitive evaluation closure")

    resolution = rulesets.data.get("validation_contract_resolution")
    if not isinstance(resolution, dict) or resolution.get("same_dispatch_identity_same_contract_content") is not True:
        ctx.error("VALIDATION_DISPATCH_IMMUTABILITY_DECLARATION_MISSING", rulesets.path, "$.validation_contract_resolution.same_dispatch_identity_same_contract_content", "validation dispatch identity must resolve immutable contract content")

    bootstrap = rulesets.data.get("immutable_resolution_bootstrap")
    roots = bootstrap.get("acceptable_roots") if isinstance(bootstrap, dict) else None
    if not isinstance(roots, list) or not roots:
        ctx.error("IMMUTABLE_RESOLUTION_BOOTSTRAP_MISSING", rulesets.path, "$.immutable_resolution_bootstrap.acceptable_roots", "host-level immutable identity roots must be explicitly declared")


def check_integrity_coverage(rulesets: Artifact, ctx: LintContext) -> Coverage:
    obj = rulesets.data.get("specification_integrity_checks")
    declared: List[str] = []
    if not isinstance(obj, dict):
        ctx.error("SPECIFICATION_INTEGRITY_CHECKS_MISSING", rulesets.path, "$.specification_integrity_checks", "specification integrity check declaration is required")
    else:
        if obj.get("required_before_model_evaluation") is not True:
            ctx.error("SPECIFICATION_INTEGRITY_NOT_PRE_EVALUATION", rulesets.path, "$.specification_integrity_checks.required_before_model_evaluation", "specification integrity must run before model evaluation")
        raw = obj.get("checks")
        if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
            ctx.error("SPECIFICATION_INTEGRITY_CHECK_LIST_INVALID", rulesets.path, "$.specification_integrity_checks.checks", "checks must be a string array")
        else:
            declared = list(raw)
            if len(declared) != len(set(declared)):
                ctx.error("SPECIFICATION_INTEGRITY_CHECK_DUPLICATE", rulesets.path, "$.specification_integrity_checks.checks", "integrity check declarations must be unique")
            for i, check in enumerate(declared):
                if check not in IMPLEMENTED_INTEGRITY_CHECKS:
                    ctx.error(
                        "SPECIFICATION_INTEGRITY_CHECK_UNIMPLEMENTED",
                        rulesets.path,
                        f"$.specification_integrity_checks.checks[{i}]",
                        f"mandatory integrity check is not implemented by cw_spec_lint v{LINTER_VERSION}: {check}",
                    )

    implemented = sorted(set(declared) & IMPLEMENTED_INTEGRITY_CHECKS)
    unimplemented = sorted(set(declared) - IMPLEMENTED_INTEGRITY_CHECKS)
    return Coverage(
        integrity_declared=declared,
        integrity_implemented=implemented,
        integrity_unimplemented=unimplemented,
        validator_required_operations=[],
        validator_scope_note="",
    )


def attach_validator_operation_coverage(ccf: Artifact, coverage: Coverage) -> None:
    validator = ccf.data.get("validator")
    ops = validator.get("required_operations") if isinstance(validator, dict) else None
    coverage.validator_required_operations = [x for x in ops if isinstance(x, str)] if isinstance(ops, list) else []
    coverage.validator_scope_note = (
        "CCF.validator.required_operations describes the full canonical model/runtime validator. "
        "cw_spec_lint validates the specification set and intentionally does not claim implementation "
        "of those runtime/model operations."
    )


def lint(scan_dir: Path) -> Tuple[LintContext, List[Artifact], Coverage]:
    ctx = LintContext()
    artifacts = discover(scan_dir, ctx)
    check_artifact_headers(artifacts, ctx)

    ccf = one_or_error(artifacts, "ccf", ctx, scan_dir)
    nodetypes = one_or_error(artifacts, "nodetypes", ctx, scan_dir)
    rulesets = one_or_error(artifacts, "rulesets", ctx, scan_dir)
    empty_coverage = Coverage([], [], [], [], "")
    if not (ccf and nodetypes and rulesets):
        return ctx, artifacts, empty_coverage

    check_cross_refs(ccf, nodetypes, rulesets, artifacts, ctx)
    idx = build_indexes(nodetypes, rulesets, ctx)

    check_nodetype_inheritance(nodetypes, idx, ctx)
    check_nodetype_properties_and_required_links(nodetypes, idx, ctx)

    check_property_rulesets(rulesets, idx, ctx)
    check_flow_patterns(rulesets, idx, ctx)
    check_link_rulesets(rulesets, idx, ctx)
    check_shared_value_types(rulesets, ctx)
    check_logic_primitive_sets(rulesets, idx, ctx)
    check_function_logic_contract(rulesets, idx, ctx)

    check_link_default_policy(rulesets, ctx)
    check_special_contracts(ccf, nodetypes, rulesets, idx, ctx)
    check_structured_scope_mechanisms(nodetypes, rulesets, idx, ctx)
    check_result_taxonomy(ccf, nodetypes, rulesets, ctx)
    check_immutable_resolution_declarations(ccf, rulesets, ctx)

    coverage = check_integrity_coverage(rulesets, ctx)
    attach_validator_operation_coverage(ccf, coverage)

    return ctx, artifacts, coverage


def sort_findings(findings: List[Finding]) -> List[Finding]:
    rank = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    return sorted(findings, key=lambda f: (rank.get(f.severity, 9), f.file, f.path, f.code, f.message))


def finding_summary_key(finding: Finding) -> Tuple[str, str]:
    patterns = [
        r"result-like token '([^']+)'",
        r"unresolved NodeType '([^']+)'",
        r"unresolved Property type '([^']+)'",
        r"link_type_ref '([^']+)'",
        r"primitive_set_ref '([^']+)'",
        r"mandatory integrity check .*: (.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, finding.message)
        if match:
            return finding.code, match.group(1)
    return finding.code, ""


def print_issue_summary(findings: List[Finding]) -> None:
    grouped = Counter(finding_summary_key(f) for f in findings if f.severity in {"ERROR", "WARNING"})
    if not grouped:
        return
    print()
    print("Issue summary:")
    severity: Dict[Tuple[str, str], str] = {}
    for f in findings:
        key = finding_summary_key(f)
        if key not in grouped:
            continue
        if severity.get(key) != "ERROR":
            severity[key] = f.severity
    for (code, detail), count in sorted(grouped.items(), key=lambda x: (0 if severity.get(x[0]) == "ERROR" else 1, x[0])):
        label = f"{code}: {detail}" if detail else code
        print(f"  {severity.get((code, detail), 'INFO'):7} {count:>3}  {label}")


def print_coverage(coverage: Coverage) -> None:
    print("Coverage:")
    print(f"  specification_integrity_checks: {len(coverage.integrity_implemented)}/{len(coverage.integrity_declared)} implemented")
    if coverage.integrity_unimplemented:
        print("  unimplemented:")
        for item in coverage.integrity_unimplemented:
            print(f"    - {item}")
    print(f"  CCF validator.required_operations declared: {len(coverage.validator_required_operations)}")
    print(f"  note: {coverage.validator_scope_note}")


def print_human(scan_dir: Path, artifacts: List[Artifact], findings: List[Finding], coverage: Coverage, show_coverage: bool) -> None:
    print(f"CW spec lint v{LINTER_VERSION}: {scan_dir}")
    print()
    known = [a for a in artifacts if a.kind != "other"]
    if known:
        print("Discovered:")
        for art in sorted(known, key=lambda a: a.kind):
            version = f" v{art.version}" if art.version else ""
            print(f"  {art.kind:10} {art.path.name}{version}")
        print()

    for finding in sort_findings(findings):
        print(f"{finding.severity:7} {finding.code}")
        print(f"        {Path(finding.file).name} {finding.path}")
        print(f"        {finding.message}")

    print_issue_summary(findings)
    if show_coverage:
        print()
        print_coverage(coverage)

    errors = sum(f.severity == "ERROR" for f in findings)
    warnings = sum(f.severity == "WARNING" for f in findings)
    infos = sum(f.severity == "INFO" for f in findings)
    print()
    if errors:
        print(f"FAIL: {errors} error(s), {warnings} warning(s), {infos} info")
    else:
        print(f"PASS: 0 errors, {warnings} warning(s), {infos} info")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint the CanonicalWireframe specification set.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="spec directory; default is the repository/spec parent of this script",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--coverage", action="store_true", help="show specification-integrity and validator-scope coverage")
    args = parser.parse_args()

    try:
        default_dir = Path(__file__).resolve().parent.parent
        scan_dir = (args.dir if args.dir is not None else default_dir).resolve()
        ctx, artifacts, coverage = lint(scan_dir)

        if args.json:
            payload = {
                "linter_version": LINTER_VERSION,
                "scan_dir": str(scan_dir),
                "artifacts": [
                    {"file": str(a.path), "kind": a.kind, "id": a.id, "version": a.version}
                    for a in artifacts
                ],
                "findings": [asdict(f) for f in sort_findings(ctx.findings)],
                "summary": {
                    "errors": sum(f.severity == "ERROR" for f in ctx.findings),
                    "warnings": sum(f.severity == "WARNING" for f in ctx.findings),
                    "infos": sum(f.severity == "INFO" for f in ctx.findings),
                },
                "coverage": asdict(coverage),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_human(scan_dir, artifacts, ctx.findings, coverage, args.coverage)

        return 1 if any(f.severity == "ERROR" for f in ctx.findings) else 0
    except Exception as exc:
        print(f"cw_spec_lint: operational failure: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
