#!/usr/bin/env python3
"""
CanonicalWireframe specification linter.

Placement:
    specs/cw_spec_lint.py

Default behavior:
    - scans every *.json file in the same directory as this script
    - discovers CCF / CW NodeTypes / CW Rulesets by CONTENT, not filename
    - does not depend on artifact version numbers
    - never modifies specification files

Usage:
    python cw_spec_lint.py
    python cw_spec_lint.py --json
    python cw_spec_lint.py --dir /path/to/specs

Exit codes:
    0 = no errors
    1 = specification lint errors found
    2 = operational failure
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

LINTER_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    severity: str   # ERROR | WARNING | INFO
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
        self.findings.append(
            Finding(
                severity=severity,
                code=code,
                file=str(file),
                path=path or "$",
                message=message,
            )
        )

    def error(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("ERROR", code, file, path, message)

    def warn(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("WARNING", code, file, path, message)

    def info(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("INFO", code, file, path, message)


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------

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
        ctx.error(
            "JSON_PARSE_ERROR",
            path,
            "$",
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}",
        )
    except Exception as exc:
        ctx.error("JSON_PARSE_ERROR", path, "$", str(exc))
    return None


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------

@dataclass
class Artifact:
    path: Path
    data: Dict[str, Any]
    kind: str  # ccf | nodetypes | rulesets | other

    @property
    def id(self) -> Optional[str]:
        value = self.data.get("id")
        return value if isinstance(value, str) and value else None

    @property
    def version(self) -> Optional[str]:
        value = self.data.get("version")
        return value if isinstance(value, str) and value else None


def classify(data: Any) -> str:
    if not isinstance(data, dict):
        return "other"

    if data.get("type") == "canonical_contract_format":
        return "ccf"
    if data.get("id") == "CANONICAL_CONTRACT_FORMAT":
        return "ccf"

    if isinstance(data.get("nodetypes"), list) and isinstance(data.get("nodetype_schema"), dict):
        return "nodetypes"
    if data.get("id") == "CW_NODETYPES":
        return "nodetypes"

    if isinstance(data.get("property_rulesets"), list) and isinstance(data.get("link_rulesets"), list):
        return "rulesets"
    if data.get("id") == "CW_RULESETS":
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
            artifacts.append(Artifact(path=path, data=data, kind=classify(data)))
        elif data is not None:
            ctx.warn("JSON_ROOT_NOT_OBJECT", path, "$", "top-level JSON value is not an object")
    return artifacts


def one_or_error(items: Sequence[Artifact], kind: str, ctx: LintContext, scan_dir: Path) -> Optional[Artifact]:
    matches = [a for a in items if a.kind == kind]
    if len(matches) == 1:
        return matches[0]

    if not matches:
        ctx.error(
            f"{kind.upper()}_NOT_FOUND",
            scan_dir,
            "$",
            f"could not discover a {kind} artifact from JSON content",
        )
    else:
        ctx.error(
            f"{kind.upper()}_AMBIGUOUS",
            scan_dir,
            "$",
            "multiple candidate artifacts found: " + ", ".join(a.path.name for a in matches),
        )
    return None


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, dict)]


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
        p = f"{base_path}[{i}].{key}"
        if not isinstance(value, str) or not value:
            ctx.error(f"{code_prefix}_MISSING_ID", file, p, f"{key} must be a non-empty string")
            continue
        if value in out:
            ctx.error(
                f"{code_prefix}_DUPLICATE_ID",
                file,
                p,
                f"duplicate {key} {value!r}",
            )
        else:
            out[value] = item
    return out


def check_min_max(obj: Any, ctx: LintContext, file: Path, path: str, code_prefix: str) -> None:
    if not isinstance(obj, dict):
        ctx.error(f"{code_prefix}_NOT_OBJECT", file, path, "cardinality constraint must be an object")
        return

    min_v = obj.get("min")
    max_v = obj.get("max")

    for name, value in (("min", min_v), ("max", max_v)):
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            ctx.error(
                f"{code_prefix}_BAD_{name.upper()}",
                file,
                f"{path}.{name}",
                f"{name} must be a non-negative integer when present",
            )

    if (
        isinstance(min_v, int)
        and not isinstance(min_v, bool)
        and isinstance(max_v, int)
        and not isinstance(max_v, bool)
        and min_v > max_v
    ):
        ctx.error(
            f"{code_prefix}_MIN_GT_MAX",
            file,
            path,
            f"min ({min_v}) exceeds max ({max_v})",
        )


def parse_endpoint_constraint(value: str) -> Optional[Tuple[str, str]]:
    if ":" not in value:
        return None
    prefix, ref = value.split(":", 1)
    if prefix in {"entity_nodetype", "property"} and ref:
        return prefix, ref
    return None


def walk_strings(value: Any, path: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield from walk_strings(child, child_path)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk_strings(child, f"{path}[{i}]")
    elif isinstance(value, str):
        yield path, value


# ---------------------------------------------------------------------------
# Cross-artifact checks
# ---------------------------------------------------------------------------

def check_artifact_ids(artifacts: Sequence[Artifact], ctx: LintContext) -> None:
    seen: Dict[str, Path] = {}
    for art in artifacts:
        if not art.id:
            continue
        if art.id in seen:
            ctx.error(
                "ARTIFACT_DUPLICATE_ID",
                art.path,
                "$.id",
                f"artifact id {art.id!r} also declared by {seen[art.id].name}",
            )
        else:
            seen[art.id] = art.path


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
            ctx.error(
                "CROSS_REF_MISMATCH",
                art.path,
                f"$.{field}",
                f"{field}={value!r}, expected discovered artifact id {expected_id!r}",
            )
        elif value not in ids:
            ctx.error(
                "CROSS_REF_UNRESOLVED",
                art.path,
                f"$.{field}",
                f"{field}={value!r} does not resolve to a discovered artifact id",
            )

    require_ref(nodetypes, "ccf_ref", ccf.id)
    require_ref(rulesets, "ccf_ref", ccf.id)
    require_ref(rulesets, "nodetypes_ref", nodetypes.id)

    dep = ccf.data.get("dependency_rules")
    if isinstance(dep, dict):
        companion = dep.get("companion_ref")
        if isinstance(companion, str):
            if rulesets.id and companion != rulesets.id:
                ctx.error(
                    "CCF_COMPANION_REF_MISMATCH",
                    ccf.path,
                    "$.dependency_rules.companion_ref",
                    f"companion_ref={companion!r}, discovered Rulesets id={rulesets.id!r}",
                )
            elif companion not in ids:
                ctx.error(
                    "CCF_COMPANION_REF_UNRESOLVED",
                    ccf.path,
                    "$.dependency_rules.companion_ref",
                    f"companion_ref={companion!r} does not resolve in scanned directory",
                )

        base_ref = dep.get("ruleset_ref")
        ownership = dep.get("ownership")
        if isinstance(base_ref, str) and base_ref not in ids:
            if ownership == "external_inherited_standard":
                ctx.warn(
                    "EXTERNAL_BASE_RULESET_NOT_IN_DIRECTORY",
                    ccf.path,
                    "$.dependency_rules.ruleset_ref",
                    f"{base_ref!r} is declared external_inherited_standard and is not present in this directory; "
                    "the linter cannot verify that external closure member",
                )
            else:
                ctx.error(
                    "CCF_BASE_RULESET_REF_UNRESOLVED",
                    ccf.path,
                    "$.dependency_rules.ruleset_ref",
                    f"{base_ref!r} does not resolve in scanned directory",
                )


# ---------------------------------------------------------------------------
# Ruleset / NodeType indexes and validation
# ---------------------------------------------------------------------------

@dataclass
class Indexes:
    nodetypes: Dict[str, Dict[str, Any]]
    property_rulesets_by_id: Dict[str, Dict[str, Any]]
    link_rulesets_by_id: Dict[str, Dict[str, Any]]
    property_types: Dict[str, List[Dict[str, Any]]]
    link_types: Dict[str, List[Dict[str, Any]]]
    flow_patterns: Set[str]


def build_indexes(nodetypes: Artifact, rulesets: Artifact, ctx: LintContext) -> Indexes:
    nt_items = list_of_dicts(nodetypes.data.get("nodetypes"))
    pr_items = list_of_dicts(rulesets.data.get("property_rulesets"))
    lr_items = list_of_dicts(rulesets.data.get("link_rulesets"))

    nt_by_id = index_unique(nt_items, "id", ctx, nodetypes.path, "$.nodetypes", "NODETYPE")
    pr_by_id = index_unique(pr_items, "id", ctx, rulesets.path, "$.property_rulesets", "PROPERTY_RULESET")
    lr_by_id = index_unique(lr_items, "id", ctx, rulesets.path, "$.link_rulesets", "LINK_RULESET")

    property_types: Dict[str, List[Dict[str, Any]]] = {}
    for i, rule in enumerate(pr_items):
        ptype = rule.get("property_type_ref")
        if not isinstance(ptype, str) or not ptype:
            ctx.error(
                "PROPERTY_RULESET_MISSING_PROPERTY_TYPE",
                rulesets.path,
                f"$.property_rulesets[{i}].property_type_ref",
                "property_type_ref must be a non-empty string",
            )
            continue
        property_types.setdefault(ptype, []).append(rule)

    for ptype, matches in property_types.items():
        if len(matches) > 1:
            ctx.error(
                "PROPERTY_TYPE_AMBIGUOUS",
                rulesets.path,
                "$.property_rulesets",
                f"property_type_ref {ptype!r} is governed by {len(matches)} Property Rulesets",
            )

    link_types: Dict[str, List[Dict[str, Any]]] = {}
    for i, rule in enumerate(lr_items):
        ltype = rule.get("link_type_ref")
        if not isinstance(ltype, str) or not ltype:
            ctx.error(
                "LINK_RULESET_MISSING_LINK_TYPE",
                rulesets.path,
                f"$.link_rulesets[{i}].link_type_ref",
                "link_type_ref must be a non-empty string",
            )
            continue
        link_types.setdefault(ltype, []).append(rule)

    for ltype, matches in link_types.items():
        if len(matches) > 1:
            ctx.error(
                "LINK_TYPE_AMBIGUOUS",
                rulesets.path,
                "$.link_rulesets",
                f"link_type_ref {ltype!r} is governed by {len(matches)} Link Rulesets",
            )

    flow_items = list_of_dicts(rulesets.data.get("flow_patterns"))
    flow_index = index_unique(flow_items, "id", ctx, rulesets.path, "$.flow_patterns", "FLOW_PATTERN")

    return Indexes(
        nodetypes=nt_by_id,
        property_rulesets_by_id=pr_by_id,
        link_rulesets_by_id=lr_by_id,
        property_types=property_types,
        link_types=link_types,
        flow_patterns=set(flow_index),
    )


def check_nodetype_inheritance(nodetypes: Artifact, idx: Indexes, ctx: LintContext) -> None:
    items = list_of_dicts(nodetypes.data.get("nodetypes"))
    graph: Dict[str, List[str]] = {}

    for i, nt in enumerate(items):
        nt_id = nt.get("id")
        if not isinstance(nt_id, str):
            continue

        parents = nt.get("extends", [])
        if parents is None:
            parents = []
        if not isinstance(parents, list):
            ctx.error(
                "NODETYPE_EXTENDS_NOT_ARRAY",
                nodetypes.path,
                f"$.nodetypes[{i}].extends",
                "extends must be an array",
            )
            graph[nt_id] = []
            continue

        valid: List[str] = []
        for j, parent in enumerate(parents):
            if not isinstance(parent, str) or parent not in idx.nodetypes:
                ctx.error(
                    "NODETYPE_EXTENDS_UNRESOLVED",
                    nodetypes.path,
                    f"$.nodetypes[{i}].extends[{j}]",
                    f"NodeType {nt_id!r} extends unresolved NodeType {parent!r}",
                )
            else:
                valid.append(parent)
        graph[nt_id] = valid

    visiting: Set[str] = set()
    visited: Set[str] = set()
    stack: List[str] = []
    reported: Set[Tuple[str, ...]] = set()

    def dfs(node: str) -> None:
        if node in visited:
            return

        if node in visiting:
            try:
                start = stack.index(node)
                cycle = tuple(stack[start:] + [node])
            except ValueError:
                cycle = (node, node)

            if cycle not in reported:
                reported.add(cycle)
                ctx.error(
                    "NODETYPE_INHERITANCE_CYCLE",
                    nodetypes.path,
                    "$.nodetypes",
                    " -> ".join(cycle),
                )
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


def check_nodetype_properties_and_required_links(
    nodetypes: Artifact,
    idx: Indexes,
    ctx: LintContext,
) -> None:
    items = list_of_dicts(nodetypes.data.get("nodetypes"))
    available_property_types = set(idx.property_types)

    for i, nt in enumerate(items):
        nt_id = nt.get("id", f"<index:{i}>")

        for field in ("required_property_types", "owned_property_types"):
            values = nt.get(field)
            if not isinstance(values, list):
                ctx.error(
                    "NODETYPE_PROPERTY_TYPES_NOT_ARRAY",
                    nodetypes.path,
                    f"$.nodetypes[{i}].{field}",
                    f"{field} must be an array",
                )
                continue

            for j, ptype in enumerate(values):
                if not isinstance(ptype, str):
                    ctx.error(
                        "NODETYPE_PROPERTY_TYPE_INVALID",
                        nodetypes.path,
                        f"$.nodetypes[{i}].{field}[{j}]",
                        "property type reference must be a string",
                    )
                    continue

                resolved = ptype in available_property_types or (ptype == "link" and bool(idx.link_types))
                if not resolved:
                    ctx.error(
                        "NODETYPE_PROPERTY_TYPE_UNRESOLVED",
                        nodetypes.path,
                        f"$.nodetypes[{i}].{field}[{j}]",
                        f"NodeType {nt_id!r} references unresolved property type {ptype!r}",
                    )

        cardinality = nt.get("property_cardinality")
        if cardinality is not None:
            if not isinstance(cardinality, dict):
                ctx.error(
                    "NODETYPE_CARDINALITY_NOT_OBJECT",
                    nodetypes.path,
                    f"$.nodetypes[{i}].property_cardinality",
                    "property_cardinality must be an object",
                )
            else:
                for ptype, limits in cardinality.items():
                    resolved = ptype in available_property_types or (ptype == "link" and bool(idx.link_types))
                    if not resolved:
                        ctx.error(
                            "NODETYPE_CARDINALITY_PROPERTY_UNRESOLVED",
                            nodetypes.path,
                            f"$.nodetypes[{i}].property_cardinality.{ptype}",
                            f"cardinality references unresolved property type {ptype!r}",
                        )
                    check_min_max(
                        limits,
                        ctx,
                        nodetypes.path,
                        f"$.nodetypes[{i}].property_cardinality.{ptype}",
                        "NODETYPE_CARDINALITY",
                    )

        required_links = nt.get("required_links", [])
        if required_links is None:
            required_links = []

        if not isinstance(required_links, list):
            ctx.error(
                "REQUIRED_LINKS_NOT_ARRAY",
                nodetypes.path,
                f"$.nodetypes[{i}].required_links",
                "required_links must be an array",
            )
            continue

        local_ids: Set[str] = set()

        for j, req in enumerate(required_links):
            p = f"$.nodetypes[{i}].required_links[{j}]"
            if not isinstance(req, dict):
                ctx.error("REQUIRED_LINK_NOT_OBJECT", nodetypes.path, p, "Required Link entry must be an object")
                continue

            for required_field in ("id", "link_type_ref", "self_role", "min"):
                if required_field not in req:
                    ctx.error(
                        "REQUIRED_LINK_REQUIRED_FIELD_MISSING",
                        nodetypes.path,
                        f"{p}.{required_field}",
                        f"Required Link is missing {required_field!r}",
                    )

            req_id = req.get("id")
            if isinstance(req_id, str) and req_id:
                if req_id in local_ids:
                    ctx.error(
                        "REQUIRED_LINK_DUPLICATE_ID",
                        nodetypes.path,
                        f"{p}.id",
                        f"duplicate Required Link id {req_id!r} in NodeType {nt_id!r}",
                    )
                local_ids.add(req_id)

            ltype = req.get("link_type_ref")
            matches = idx.link_types.get(ltype, []) if isinstance(ltype, str) else []

            if len(matches) != 1:
                ctx.error(
                    "REQUIRED_LINK_TYPE_UNRESOLVED_OR_AMBIGUOUS",
                    nodetypes.path,
                    f"{p}.link_type_ref",
                    f"link_type_ref {ltype!r} resolves to {len(matches)} Link Rulesets",
                )
            else:
                rule = matches[0]
                roles = set(rule.get("semantic_roles", {}).values()) if isinstance(rule.get("semantic_roles"), dict) else set()
                self_role = req.get("self_role")
                if not isinstance(self_role, str) or self_role not in roles:
                    ctx.error(
                        "REQUIRED_LINK_SELF_ROLE_UNRESOLVED",
                        nodetypes.path,
                        f"{p}.self_role",
                        f"self_role {self_role!r} does not resolve in Link Ruleset semantic_roles",
                    )

            check_min_max(req, ctx, nodetypes.path, p, "REQUIRED_LINK_CARDINALITY")

            other = req.get("other_endpoint")
            if other is not None:
                if not isinstance(other, dict):
                    ctx.error(
                        "REQUIRED_LINK_OTHER_ENDPOINT_NOT_OBJECT",
                        nodetypes.path,
                        f"{p}.other_endpoint",
                        "other_endpoint must be an object",
                    )
                else:
                    nt_ref = other.get("entity_nodetype_ref")
                    if nt_ref is not None and (not isinstance(nt_ref, str) or nt_ref not in idx.nodetypes):
                        ctx.error(
                            "REQUIRED_LINK_OTHER_NODETYPE_UNRESOLVED",
                            nodetypes.path,
                            f"{p}.other_endpoint.entity_nodetype_ref",
                            f"unresolved NodeType {nt_ref!r}",
                        )
                    pt_ref = other.get("property_type_ref")
                    if pt_ref is not None:
                        resolved = isinstance(pt_ref, str) and (
                            pt_ref in idx.property_types or (pt_ref == "link" and bool(idx.link_types))
                        )
                        if not resolved:
                            ctx.error(
                                "REQUIRED_LINK_OTHER_PROPERTY_UNRESOLVED",
                                nodetypes.path,
                                f"{p}.other_endpoint.property_type_ref",
                                f"unresolved Property type {pt_ref!r}",
                            )


def check_value_schema(
    rule: Dict[str, Any],
    rulesets: Artifact,
    path: str,
    ctx: LintContext,
) -> None:
    schema = rule.get("value_schema")
    if not isinstance(schema, dict):
        ctx.error("RULESET_VALUE_SCHEMA_MISSING", rulesets.path, f"{path}.value_schema", "value_schema must be an object")
        return

    required = schema.get("required", [])
    optional = schema.get("optional", [])
    fields = schema.get("fields")

    if not isinstance(required, list):
        ctx.error("VALUE_SCHEMA_REQUIRED_NOT_ARRAY", rulesets.path, f"{path}.value_schema.required", "required must be an array")
        required = []
    if not isinstance(optional, list):
        ctx.error("VALUE_SCHEMA_OPTIONAL_NOT_ARRAY", rulesets.path, f"{path}.value_schema.optional", "optional must be an array")
        optional = []
    if not isinstance(fields, dict):
        ctx.error("VALUE_SCHEMA_FIELDS_NOT_OBJECT", rulesets.path, f"{path}.value_schema.fields", "fields must be an object")
        return

    req_set = {x for x in required if isinstance(x, str)}
    opt_set = {x for x in optional if isinstance(x, str)}

    overlap = sorted(req_set & opt_set)
    if overlap:
        ctx.error(
            "VALUE_SCHEMA_REQUIRED_OPTIONAL_OVERLAP",
            rulesets.path,
            path,
            f"fields declared both required and optional: {overlap}",
        )

    declared = req_set | opt_set
    missing = sorted(declared - set(fields))
    if missing:
        ctx.error(
            "VALUE_SCHEMA_DECLARED_FIELD_MISSING",
            rulesets.path,
            f"{path}.value_schema.fields",
            f"required/optional fields missing from fields: {missing}",
        )

    undeclared = sorted(set(fields) - declared)
    if undeclared:
        ctx.error(
            "VALUE_SCHEMA_FIELD_NOT_CLASSIFIED",
            rulesets.path,
            f"{path}.value_schema",
            f"fields must be classified required or optional: {undeclared}",
        )


def check_property_rulesets(rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    items = list_of_dicts(rulesets.data.get("property_rulesets"))

    for i, rule in enumerate(items):
        p = f"$.property_rulesets[{i}]"
        check_value_schema(rule, rulesets, p, ctx)

        schema = rule.get("value_schema")
        if not isinstance(schema, dict):
            continue

        fields = schema.get("fields")
        if not isinstance(fields, dict):
            continue

        reference_fields: Set[str] = set()
        for field, type_decl in fields.items():
            if not isinstance(type_decl, str):
                continue
            if (
                "canonical_ref" in type_decl
                or "canonical_or_external_ref" in type_decl
                or type_decl == "external_ref"
            ):
                reference_fields.add(field)

        constraints = rule.get("reference_constraints")
        if reference_fields:
            if not isinstance(constraints, dict):
                ctx.error(
                    "REFERENCE_CONSTRAINT_POLICY_MISSING",
                    rulesets.path,
                    f"{p}.reference_constraints",
                    f"reference-bearing fields require explicit reference_constraints: {sorted(reference_fields)}",
                )
                continue

            for field in sorted(reference_fields):
                if field not in constraints:
                    ctx.error(
                        "REFERENCE_CONSTRAINT_FIELD_MISSING",
                        rulesets.path,
                        f"{p}.reference_constraints.{field}",
                        f"reference-bearing field {field!r} has no explicit compatibility policy",
                    )

        if isinstance(constraints, dict):
            for field, policy in constraints.items():
                cp = f"{p}.reference_constraints.{field}"
                if field not in fields:
                    ctx.error(
                        "REFERENCE_CONSTRAINT_UNKNOWN_FIELD",
                        rulesets.path,
                        cp,
                        f"reference_constraints declared for unknown value_schema field {field!r}",
                    )
                if not isinstance(policy, dict):
                    ctx.error("REFERENCE_CONSTRAINT_NOT_OBJECT", rulesets.path, cp, "reference constraint policy must be an object")
                    continue

                allowed_nts = policy.get("allowed_nodetype_refs")
                if allowed_nts is not None:
                    if not isinstance(allowed_nts, list):
                        ctx.error("ALLOWED_NODETYPES_NOT_ARRAY", rulesets.path, f"{cp}.allowed_nodetype_refs", "must be an array")
                    else:
                        for j, nt_ref in enumerate(allowed_nts):
                            if not isinstance(nt_ref, str) or nt_ref not in idx.nodetypes:
                                ctx.error(
                                    "REFERENCE_CONSTRAINT_NODETYPE_UNRESOLVED",
                                    rulesets.path,
                                    f"{cp}.allowed_nodetype_refs[{j}]",
                                    f"unresolved NodeType {nt_ref!r}",
                                )


def check_link_rulesets(rulesets: Artifact, idx: Indexes, ctx: LintContext) -> None:
    items = list_of_dicts(rulesets.data.get("link_rulesets"))

    for i, rule in enumerate(items):
        p = f"$.link_rulesets[{i}]"
        check_value_schema(rule, rulesets, p, ctx)

        roles_obj = rule.get("semantic_roles")
        if not isinstance(roles_obj, dict) or not roles_obj:
            ctx.error("LINK_RULESET_SEMANTIC_ROLES_MISSING", rulesets.path, f"{p}.semantic_roles", "semantic_roles must be a non-empty object")
            roles: Set[str] = set()
        else:
            roles = {v for v in roles_obj.values() if isinstance(v, str)}
            if "parent_ref" not in roles_obj or "child_ref" not in roles_obj:
                ctx.error(
                    "LINK_RULESET_ENDPOINT_ROLES_INCOMPLETE",
                    rulesets.path,
                    f"{p}.semantic_roles",
                    "Link Ruleset must define semantic roles for parent_ref and child_ref",
                )

        owner = rule.get("property_owner")
        if not isinstance(owner, str) or owner not in roles:
            ctx.error(
                "LINK_RULESET_PROPERTY_OWNER_UNRESOLVED",
                rulesets.path,
                f"{p}.property_owner",
                f"property_owner {owner!r} does not resolve to one of semantic role values {sorted(roles)}",
            )

        impact = rule.get("unresolved_impact")
        if impact is not None:
            if not isinstance(impact, dict):
                ctx.error("UNRESOLVED_IMPACT_NOT_OBJECT", rulesets.path, f"{p}.unresolved_impact", "unresolved_impact must be an object")
            else:
                for field in ("from_role", "to_role"):
                    value = impact.get(field)
                    if not isinstance(value, str) or value not in roles:
                        ctx.error(
                            "UNRESOLVED_IMPACT_ROLE_UNRESOLVED",
                            rulesets.path,
                            f"{p}.unresolved_impact.{field}",
                            f"{field} {value!r} does not resolve to a semantic role",
                        )

        deriv = rule.get("dependency_derivation")
        if deriv is not None:
            if not isinstance(deriv, dict):
                ctx.error("DEPENDENCY_DERIVATION_NOT_OBJECT", rulesets.path, f"{p}.dependency_derivation", "dependency_derivation must be an object")
            else:
                if deriv.get("dependency_forming") is True:
                    for field in ("used_role", "consumer_role"):
                        value = deriv.get(field)
                        if not isinstance(value, str) or value not in roles:
                            ctx.error(
                                "DEPENDENCY_DERIVATION_ROLE_UNRESOLVED",
                                rulesets.path,
                                f"{p}.dependency_derivation.{field}",
                                f"{field} {value!r} does not resolve to a semantic role",
                            )

        flow = rule.get("flow")
        if flow is not None:
            if not isinstance(flow, dict):
                ctx.error("FLOW_NOT_OBJECT", rulesets.path, f"{p}.flow", "flow must be an object")
            else:
                direct = flow.get("pattern_ref")
                if direct is not None:
                    if not isinstance(direct, str) or direct not in idx.flow_patterns:
                        ctx.error(
                            "FLOW_PATTERN_UNRESOLVED",
                            rulesets.path,
                            f"{p}.flow.pattern_ref",
                            f"unresolved flow pattern {direct!r}",
                        )

                cases = flow.get("cases")
                if cases is not None:
                    if not isinstance(cases, list):
                        ctx.error("FLOW_CASES_NOT_ARRAY", rulesets.path, f"{p}.flow.cases", "flow cases must be an array")
                    else:
                        for j, case in enumerate(cases):
                            cp = f"{p}.flow.cases[{j}]"
                            if not isinstance(case, dict):
                                ctx.error("FLOW_CASE_NOT_OBJECT", rulesets.path, cp, "flow case must be an object")
                                continue
                            nt_ref = case.get("parent_owner_nodetype_ref")
                            if not isinstance(nt_ref, str) or nt_ref not in idx.nodetypes:
                                ctx.error(
                                    "FLOW_CASE_NODETYPE_UNRESOLVED",
                                    rulesets.path,
                                    f"{cp}.parent_owner_nodetype_ref",
                                    f"unresolved NodeType {nt_ref!r}",
                                )
                            pattern = case.get("pattern_ref")
                            if not isinstance(pattern, str) or pattern not in idx.flow_patterns:
                                ctx.error(
                                    "FLOW_CASE_PATTERN_UNRESOLVED",
                                    rulesets.path,
                                    f"{cp}.pattern_ref",
                                    f"unresolved flow pattern {pattern!r}",
                                )

                excluded = flow.get("excluded_nodetype_refs")
                if isinstance(excluded, dict):
                    for nt_ref in excluded:
                        if nt_ref not in idx.nodetypes:
                            ctx.error(
                                "FLOW_EXCLUDED_NODETYPE_UNRESOLVED",
                                rulesets.path,
                                f"{p}.flow.excluded_nodetype_refs.{nt_ref}",
                                f"unresolved NodeType {nt_ref!r}",
                            )

        endpoint_constraints = rule.get("endpoint_constraints")
        if endpoint_constraints is not None:
            if not isinstance(endpoint_constraints, dict):
                ctx.error(
                    "ENDPOINT_CONSTRAINTS_NOT_OBJECT",
                    rulesets.path,
                    f"{p}.endpoint_constraints",
                    "endpoint_constraints must be an object",
                )
            else:
                for endpoint, constraints in endpoint_constraints.items():
                    ep = f"{p}.endpoint_constraints.{endpoint}"
                    if endpoint not in {"parent_ref", "child_ref"}:
                        ctx.error(
                            "ENDPOINT_CONSTRAINT_UNKNOWN_ENDPOINT",
                            rulesets.path,
                            ep,
                            f"unknown Link endpoint {endpoint!r}",
                        )
                    if not isinstance(constraints, list):
                        ctx.error("ENDPOINT_CONSTRAINT_NOT_ARRAY", rulesets.path, ep, "endpoint constraint must be an array")
                        continue
                    for j, constraint in enumerate(constraints):
                        cp = f"{ep}[{j}]"
                        if not isinstance(constraint, str):
                            ctx.error("ENDPOINT_CONSTRAINT_NOT_STRING", rulesets.path, cp, "endpoint constraint must be a string")
                            continue
                        parsed = parse_endpoint_constraint(constraint)
                        if parsed is None:
                            ctx.error(
                                "ENDPOINT_CONSTRAINT_UNKNOWN_SYNTAX",
                                rulesets.path,
                                cp,
                                f"unsupported endpoint constraint syntax {constraint!r}",
                            )
                            continue
                        kind, ref = parsed
                        if kind == "entity_nodetype" and ref not in idx.nodetypes:
                            ctx.error(
                                "ENDPOINT_NODETYPE_UNRESOLVED",
                                rulesets.path,
                                cp,
                                f"unresolved NodeType {ref!r}",
                            )
                        elif kind == "property":
                            resolved = ref in idx.property_types or (ref == "link" and bool(idx.link_types))
                            if not resolved:
                                ctx.error(
                                    "ENDPOINT_PROPERTY_TYPE_UNRESOLVED",
                                    rulesets.path,
                                    cp,
                                    f"unresolved Property type {ref!r}",
                                )


# ---------------------------------------------------------------------------
# Mirror / vocabulary checks
# ---------------------------------------------------------------------------

def check_ccf_vocabulary(ccf: Artifact, idx: Indexes, ctx: LintContext) -> None:
    event_model = ccf.data.get("event_model")
    if isinstance(event_model, dict):
        refs = event_model.get("canonical_reference_links")
        if isinstance(refs, list):
            for i, ref in enumerate(refs):
                if not isinstance(ref, str) or ref not in idx.link_types:
                    ctx.error(
                        "CCF_EVENT_LINK_TYPE_UNRESOLVED",
                        ccf.path,
                        f"$.event_model.canonical_reference_links[{i}]",
                        f"CCF event link specialization {ref!r} does not resolve in CW Rulesets",
                    )

    effect_model = ccf.data.get("effect_model")
    if isinstance(effect_model, dict):
        text = effect_model.get("rule")
        if isinstance(text, str) and "effect_target" in text and "effect_target" not in idx.link_types:
            ctx.error(
                "CCF_EFFECT_TARGET_UNRESOLVED",
                ccf.path,
                "$.effect_model.rule",
                "CCF requires effect_target but CW Rulesets do not declare it",
            )


def check_nodetype_contract_refs(nodetypes: Artifact, idx: Indexes, ctx: LintContext) -> None:
    binding_model = nodetypes.data.get("binding_model")
    if isinstance(binding_model, dict):
        consumer = binding_model.get("consumer_nodetype_ref")
        if consumer is not None and (not isinstance(consumer, str) or consumer not in idx.nodetypes):
            ctx.error(
                "BINDING_CONSUMER_NODETYPE_UNRESOLVED",
                nodetypes.path,
                "$.binding_model.consumer_nodetype_ref",
                f"unresolved NodeType {consumer!r}",
            )

    output_contract = nodetypes.data.get("output_source_contract")
    if isinstance(output_contract, dict):
        allowed = output_contract.get("allowed_source_link_types")
        if isinstance(allowed, list):
            for i, ref in enumerate(allowed):
                if not isinstance(ref, str) or ref not in idx.link_types:
                    ctx.error(
                        "OUTPUT_SOURCE_LINK_TYPE_UNRESOLVED",
                        nodetypes.path,
                        f"$.output_source_contract.allowed_source_link_types[{i}]",
                        f"unresolved Link type {ref!r}",
                    )
        card = output_contract.get("cardinality_across_allowed_source_types")
        if card is not None:
            check_min_max(
                card,
                ctx,
                nodetypes.path,
                "$.output_source_contract.cardinality_across_allowed_source_types",
                "OUTPUT_SOURCE_CARDINALITY",
            )

    api_contract = nodetypes.data.get("api_io_contract")
    api_rules = idx.property_types.get("api", [])
    if isinstance(api_contract, dict) and len(api_rules) == 1:
        api_rule = api_rules[0]
        rc = api_rule.get("reference_constraints")
        if isinstance(rc, dict):
            for side in ("input_refs", "output_refs"):
                nt_side = api_contract.get(side)
                rule_side = rc.get(side)
                if isinstance(nt_side, dict) and isinstance(rule_side, dict):
                    nt_allowed = nt_side.get("allowed_nodetype_refs")
                    rule_allowed = rule_side.get("allowed_nodetype_refs")
                    if isinstance(nt_allowed, list) and isinstance(rule_allowed, list):
                        if set(nt_allowed) != set(rule_allowed):
                            ctx.error(
                                "API_IO_NODETYPE_MIRROR_MISMATCH",
                                nodetypes.path,
                                f"$.api_io_contract.{side}.allowed_nodetype_refs",
                                f"NodeTypes API contract {nt_allowed!r} differs from RULESET_API {rule_allowed!r}",
                            )

                    nt_match = nt_side.get("nodetype_matching")
                    rule_match = rule_side.get("nodetype_matching")
                    if nt_match != rule_match:
                        ctx.error(
                            "API_IO_MATCH_POLICY_MISMATCH",
                            nodetypes.path,
                            f"$.api_io_contract.{side}.nodetype_matching",
                            f"NodeTypes policy {nt_match!r} differs from RULESET_API {rule_match!r}",
                        )


# ---------------------------------------------------------------------------
# Result taxonomy checks
# ---------------------------------------------------------------------------

RESULT_TOKEN_RE = re.compile(
    r"\b(?:INVALID_[A-Z][A-Z0-9_]*|IMPLEMENTATION_FAILURE|UNREADY|READY)\b"
)


def declared_result_classes(ccf: Artifact, rulesets: Artifact) -> Set[str]:
    declared: Set[str] = set()

    model = rulesets.data.get("evaluation_result_model")
    if isinstance(model, dict):
        classes = model.get("classes")
        if isinstance(classes, dict):
            declared.update(k for k in classes if isinstance(k, str))

    validator = ccf.data.get("validator")
    if isinstance(validator, dict):
        states = validator.get("finding_states")
        if isinstance(states, list):
            for state in states:
                if isinstance(state, str):
                    upper = state.upper()
                    if upper in {
                        "INVALID_SPECIFICATION",
                        "INVALID_MODEL",
                        "IMPLEMENTATION_FAILURE",
                        "UNREADY",
                        "READY",
                    }:
                        declared.add(upper)

    return declared


def check_result_taxonomy(
    ccf: Artifact,
    nodetypes: Artifact,
    rulesets: Artifact,
    ctx: LintContext,
) -> None:
    declared = declared_result_classes(ccf, rulesets)

    if not declared:
        ctx.error(
            "RESULT_TAXONOMY_MISSING",
            rulesets.path,
            "$.evaluation_result_model.classes",
            "no evaluation result taxonomy could be resolved",
        )
        return

    for art in (ccf, nodetypes, rulesets):
        for path, text in walk_strings(art.data):
            for token in RESULT_TOKEN_RE.findall(text):
                if token not in declared:
                    ctx.error(
                        "UNDECLARED_RESULT_CLASS",
                        art.path,
                        path,
                        f"result-like token {token!r} is not in declared taxonomy {sorted(declared)}",
                    )


# ---------------------------------------------------------------------------
# Specification integrity declarations that can be checked mechanically
# ---------------------------------------------------------------------------

def check_link_reference_default_policy(rulesets: Artifact, ctx: LintContext) -> None:
    obj = rulesets.data.get("link_reference_compatibility")
    if not isinstance(obj, dict):
        ctx.error(
            "LINK_DEFAULT_ENDPOINT_POLICY_MISSING",
            rulesets.path,
            "$.link_reference_compatibility",
            "explicit default Link endpoint compatibility policy is missing",
        )
        return

    default = obj.get("default_endpoint_policy")
    if not isinstance(default, dict):
        ctx.error(
            "LINK_DEFAULT_ENDPOINT_POLICY_MISSING",
            rulesets.path,
            "$.link_reference_compatibility.default_endpoint_policy",
            "default_endpoint_policy must be explicitly declared",
        )


def check_required_integrity_mechanisms(rulesets: Artifact, ctx: LintContext) -> None:
    checks = rulesets.data.get("specification_integrity_checks")
    if not isinstance(checks, dict):
        ctx.error(
            "SPECIFICATION_INTEGRITY_CHECKS_MISSING",
            rulesets.path,
            "$.specification_integrity_checks",
            "Rulesets must declare specification integrity checks",
        )
        return

    if checks.get("required_before_model_evaluation") is not True:
        ctx.error(
            "SPECIFICATION_INTEGRITY_NOT_PRE_EVALUATION",
            rulesets.path,
            "$.specification_integrity_checks.required_before_model_evaluation",
            "specification integrity must be validated before model evaluation",
        )


# ---------------------------------------------------------------------------
# Main lint
# ---------------------------------------------------------------------------

def lint(scan_dir: Path) -> Tuple[LintContext, List[Artifact]]:
    ctx = LintContext()
    artifacts = discover(scan_dir, ctx)

    check_artifact_ids(artifacts, ctx)

    ccf = one_or_error(artifacts, "ccf", ctx, scan_dir)
    nodetypes = one_or_error(artifacts, "nodetypes", ctx, scan_dir)
    rulesets = one_or_error(artifacts, "rulesets", ctx, scan_dir)

    if not (ccf and nodetypes and rulesets):
        return ctx, artifacts

    check_cross_refs(ccf, nodetypes, rulesets, artifacts, ctx)

    idx = build_indexes(nodetypes, rulesets, ctx)

    check_nodetype_inheritance(nodetypes, idx, ctx)
    check_nodetype_properties_and_required_links(nodetypes, idx, ctx)
    check_property_rulesets(rulesets, idx, ctx)
    check_link_rulesets(rulesets, idx, ctx)

    check_ccf_vocabulary(ccf, idx, ctx)
    check_nodetype_contract_refs(nodetypes, idx, ctx)

    check_result_taxonomy(ccf, nodetypes, rulesets, ctx)
    check_link_reference_default_policy(rulesets, ctx)
    check_required_integrity_mechanisms(rulesets, ctx)

    return ctx, artifacts


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def sort_findings(findings: List[Finding]) -> List[Finding]:
    severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    return sorted(
        findings,
        key=lambda f: (severity_order.get(f.severity, 9), f.file, f.path, f.code, f.message),
    )



def finding_summary_key(finding: Finding) -> Tuple[str, str]:
    """
    Group repeated findings by issue class and the concrete offending token/ref
    when one can be extracted deterministically from the message.
    """
    message = finding.message

    patterns = [
        r"result-like token '([^']+)'",
        r"unresolved NodeType '([^']+)'",
        r"unresolved Property type '([^']+)'",
        r"unresolved flow pattern '([^']+)'",
        r"link_type_ref '([^']+)'",
        r"property_type_ref '([^']+)'",
        r"companion_ref='([^']+)'",
        r"field '([^']+)'",
        r"'([^']+)' is declared external_inherited_standard",
    ]

    detail = ""
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            detail = match.group(1)
            break

    return finding.code, detail


def print_issue_summary(findings: List[Finding]) -> None:
    if not findings:
        return

    grouped = Counter(
        finding_summary_key(f)
        for f in findings
        if f.severity in {"ERROR", "WARNING"}
    )

    if not grouped:
        return

    print()
    print("Issue summary:")

    severity_by_key: Dict[Tuple[str, str], str] = {}
    for finding in findings:
        key = finding_summary_key(finding)
        if key not in grouped:
            continue
        existing = severity_by_key.get(key)
        if existing != "ERROR":
            severity_by_key[key] = finding.severity

    severity_rank = {"ERROR": 0, "WARNING": 1, "INFO": 2}

    rows = sorted(
        grouped.items(),
        key=lambda item: (
            severity_rank.get(severity_by_key.get(item[0], "INFO"), 9),
            item[0][0],
            item[0][1],
        ),
    )

    for (code, detail), count in rows:
        severity = severity_by_key.get((code, detail), "INFO")
        label = f"{code}: {detail}" if detail else code
        print(f"  {severity:7} {count:>3}  {label}")


def print_human(scan_dir: Path, artifacts: List[Artifact], findings: List[Finding]) -> None:
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
        file_name = Path(finding.file).name
        print(f"{finding.severity:7} {finding.code}")
        print(f"        {file_name} {finding.path}")
        print(f"        {finding.message}")

    errors = sum(f.severity == "ERROR" for f in findings)
    warnings = sum(f.severity == "WARNING" for f in findings)
    infos = sum(f.severity == "INFO" for f in findings)

    print_issue_summary(findings)

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
        default=Path("../"),
        help="spec directory; defaults to ../ relative to the current working directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON findings",
    )
    args = parser.parse_args()

    try:
        scan_dir = args.dir.resolve()
        ctx, artifacts = lint(scan_dir)

        if args.json:
            payload = {
                "scan_dir": str(scan_dir),
                "artifacts": [
                    {
                        "file": str(a.path),
                        "kind": a.kind,
                        "id": a.id,
                        "version": a.version,
                    }
                    for a in artifacts
                ],
                "findings": [asdict(f) for f in sort_findings(ctx.findings)],
                "summary": {
                    "errors": sum(f.severity == "ERROR" for f in ctx.findings),
                    "warnings": sum(f.severity == "WARNING" for f in ctx.findings),
                    "infos": sum(f.severity == "INFO" for f in ctx.findings),
                },
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_human(scan_dir, artifacts, ctx.findings)

        return 1 if any(f.severity == "ERROR" for f in ctx.findings) else 0

    except Exception as exc:
        print(f"cw_spec_lint: operational failure: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
