#!/usr/bin/env python3
"""
Validate arbitrary CanonicalWireframe artifacts against the local locked CW standard.

Input may be either:

    python linter/cw_validate.py artifact.json
    python linter/cw_validate.py path/to/artifact-directory

A directory is treated as one validation set. All *.json files below the directory
are loaded recursively and canonical references may resolve across those files.
Filenames and directory structure never provide semantic meaning.

By default the validator resolves the CW standard from the repository root relative
to this script:

    ../Canonical_Contract_Format_v*.json
    ../CanonicalWireframe_NodeTypes_v*.json
    ../CanonicalWireframe_Dependency_Rules_v*.json

Use --spec-dir only to explicitly validate against another specification directory.

This tool validates CW artifacts. `cw_spec_lint.py` is separate and validates the
CW standard set itself.

Exit codes:
    0 = READY or UNREADY (canonical model is valid)
    1 = INVALID_MODEL or INVALID_SPECIFICATION
    2 = IMPLEMENTATION_FAILURE
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

VALIDATOR_VERSION = "1.0.0"


class DuplicateKeyError(ValueError):
    pass


@dataclass
class Finding:
    severity: str
    code: str
    file: str
    path: str
    message: str


@dataclass
class ContractDocument:
    path: Path
    data: Dict[str, Any]


@dataclass
class Standard:
    ccf_path: Path
    ccf: Dict[str, Any]
    nodetypes_path: Path
    nodetypes: Dict[str, Any]
    rulesets_path: Path
    rulesets: Dict[str, Any]


class Context:
    def __init__(self) -> None:
        self.findings: List[Finding] = []
        self.unready_reasons: List[str] = []

    def add(self, severity: str, code: str, file: Path | str, path: str, message: str) -> None:
        self.findings.append(Finding(severity, code, str(file), path or "$", message))

    def error(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("ERROR", code, file, path, message)

    def warn(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("WARNING", code, file, path, message)

    def unready(self, code: str, file: Path | str, path: str, message: str) -> None:
        self.add("UNREADY", code, file, path, message)
        self.unready_reasons.append(message)


def reject_duplicate_keys(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def read_json(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value must be an object")
    return data


def classify_spec(data: Mapping[str, Any]) -> Optional[str]:
    if data.get("id") == "CANONICAL_CONTRACT_FORMAT" or data.get("type") == "canonical_contract_format":
        return "ccf"
    if data.get("id") == "CW_NODETYPES":
        return "nodetypes"
    if data.get("id") == "CW_RULESETS":
        return "rulesets"
    return None


def load_standard(spec_dir: Path) -> Standard:
    found: Dict[str, List[Tuple[Path, Dict[str, Any]]]] = {"ccf": [], "nodetypes": [], "rulesets": []}
    for path in sorted(spec_dir.glob("*.json")):
        try:
            data = read_json(path)
        except Exception:
            continue
        kind = classify_spec(data)
        if kind:
            found[kind].append((path, data))

    missing = [kind for kind, values in found.items() if not values]
    ambiguous = [kind for kind, values in found.items() if len(values) > 1]
    if missing:
        raise RuntimeError(f"missing specification artifact(s): {', '.join(missing)}")
    if ambiguous:
        detail = "; ".join(f"{kind}={len(found[kind])}" for kind in ambiguous)
        raise RuntimeError(f"ambiguous specification artifacts: {detail}")

    return Standard(
        ccf_path=found["ccf"][0][0],
        ccf=found["ccf"][0][1],
        nodetypes_path=found["nodetypes"][0][0],
        nodetypes=found["nodetypes"][0][1],
        rulesets_path=found["rulesets"][0][0],
        rulesets=found["rulesets"][0][1],
    )


def lint_standard(spec_dir: Path) -> Tuple[bool, str]:
    """Run the sibling standard self-linter when available."""
    lint_path = Path(__file__).resolve().with_name("cw_spec_lint.py")
    if not lint_path.exists():
        return True, "cw_spec_lint.py not present; standard self-lint skipped"
    try:
        spec = importlib.util.spec_from_file_location("cw_spec_lint", lint_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not import cw_spec_lint.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        lint_ctx, _artifacts, _coverage = module.lint(spec_dir)
        errors = [f for f in lint_ctx.findings if f.severity == "ERROR"]
        if errors:
            return False, f"CW standard self-lint failed with {len(errors)} error(s)"
        return True, "CW standard self-lint passed"
    except Exception as exc:
        return False, f"CW standard self-lint could not execute: {exc}"


def load_input(input_path: Path, ctx: Context) -> List[ContractDocument]:
    if not input_path.exists():
        raise RuntimeError(f"input does not exist: {input_path}")

    paths: List[Path]
    if input_path.is_file():
        if input_path.suffix.lower() != ".json":
            raise RuntimeError("single-file input must be a .json file")
        paths = [input_path]
    elif input_path.is_dir():
        paths = sorted(p for p in input_path.rglob("*.json") if p.is_file())
        if not paths:
            raise RuntimeError("input directory contains no .json files")
    else:
        raise RuntimeError("input must be a JSON file or directory")

    docs: List[ContractDocument] = []
    for path in paths:
        try:
            docs.append(ContractDocument(path, read_json(path)))
        except DuplicateKeyError as exc:
            ctx.error("JSON_DUPLICATE_KEY", path, "$", str(exc))
        except json.JSONDecodeError as exc:
            ctx.error("JSON_PARSE_ERROR", path, "$", f"{exc.msg} at line {exc.lineno}, column {exc.colno}")
        except Exception as exc:
            ctx.error("JSON_LOAD_ERROR", path, "$", str(exc))
    return docs


def as_dict_list(value: Any) -> List[Dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def index_standard(standard: Standard) -> Dict[str, Any]:
    nodetypes = {x["id"]: x for x in as_dict_list(standard.nodetypes.get("nodetypes")) if isinstance(x.get("id"), str)}
    prop_rules_by_id = {x["id"]: x for x in as_dict_list(standard.rulesets.get("property_rulesets")) if isinstance(x.get("id"), str)}
    prop_rules_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for rule in prop_rules_by_id.values():
        ref = rule.get("property_type_ref")
        if isinstance(ref, str):
            prop_rules_by_type.setdefault(ref, []).append(rule)

    link_rules_by_id = {x["id"]: x for x in as_dict_list(standard.rulesets.get("link_rulesets")) if isinstance(x.get("id"), str)}
    link_rules_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for rule in link_rules_by_id.values():
        ref = rule.get("link_type_ref")
        if isinstance(ref, str):
            link_rules_by_type.setdefault(ref, []).append(rule)

    return {
        "nodetypes": nodetypes,
        "prop_rules_by_id": prop_rules_by_id,
        "prop_rules_by_type": prop_rules_by_type,
        "link_rules_by_id": link_rules_by_id,
        "link_rules_by_type": link_rules_by_type,
    }


def effective_nodetype(nt_id: str, nodetypes: Mapping[str, Dict[str, Any]], cache: Dict[str, Dict[str, Any]], stack: Optional[Set[str]] = None) -> Dict[str, Any]:
    if nt_id in cache:
        return cache[nt_id]
    if nt_id not in nodetypes:
        raise KeyError(nt_id)
    stack = set() if stack is None else set(stack)
    if nt_id in stack:
        raise RuntimeError(f"NodeType inheritance cycle at {nt_id}")
    stack.add(nt_id)

    source = nodetypes[nt_id]
    required_props: List[str] = []
    owned_props: List[str] = []
    required_links: List[Dict[str, Any]] = []
    cardinality: Dict[str, Dict[str, Any]] = {}

    for parent in source.get("extends", []) if isinstance(source.get("extends"), list) else []:
        if not isinstance(parent, str):
            continue
        inherited = effective_nodetype(parent, nodetypes, cache, stack)
        for x in inherited["required_property_types"]:
            if x not in required_props:
                required_props.append(x)
        for x in inherited["owned_property_types"]:
            if x not in owned_props:
                owned_props.append(x)
        for req in inherited["required_links"]:
            required_links.append(dict(req))
        cardinality.update({k: dict(v) for k, v in inherited["property_cardinality"].items()})

    for x in source.get("required_property_types", []) if isinstance(source.get("required_property_types"), list) else []:
        if isinstance(x, str) and x not in required_props:
            required_props.append(x)
    for x in source.get("owned_property_types", []) if isinstance(source.get("owned_property_types"), list) else []:
        if isinstance(x, str) and x not in owned_props:
            owned_props.append(x)
    for req in source.get("required_links", []) if isinstance(source.get("required_links"), list) else []:
        if isinstance(req, dict):
            required_links.append(dict(req))
    if isinstance(source.get("property_cardinality"), dict):
        cardinality.update({k: dict(v) for k, v in source["property_cardinality"].items() if isinstance(v, dict)})

    result = {
        "required_property_types": required_props,
        "owned_property_types": owned_props,
        "required_links": required_links,
        "property_cardinality": cardinality,
    }
    cache[nt_id] = result
    return result


def validate_contract_shape(doc: ContractDocument, standard: Standard, ctx: Context) -> None:
    shape = standard.ccf.get("contract_shape")
    if not isinstance(shape, dict):
        raise RuntimeError("CCF contract_shape missing")

    required = shape.get("required", [])
    optional = shape.get("optional", [])
    allowed = set(x for x in required + optional if isinstance(x, str))
    for field in required if isinstance(required, list) else []:
        if field not in doc.data:
            ctx.error("CONTRACT_REQUIRED_FIELD_MISSING", doc.path, f"$.{field}", f"missing required CCF field {field!r}")

    # Unknown top-level extension fields are not rejected automatically because CCF
    # explicitly supports non-core extension points. Core fields are still validated.

    fmt = doc.data.get("format")
    fmt_contract = shape.get("format")
    if not isinstance(fmt, dict):
        ctx.error("FORMAT_INVALID", doc.path, "$.format", "format must be an object")
    elif isinstance(fmt_contract, dict):
        for field in fmt_contract.get("required", []) if isinstance(fmt_contract.get("required"), list) else []:
            if field not in fmt:
                ctx.error("FORMAT_REQUIRED_FIELD_MISSING", doc.path, f"$.format.{field}", f"missing format field {field!r}")
        expected_cf = fmt_contract.get("contract_format")
        expected_fv = fmt_contract.get("format_version")
        if expected_cf is not None and fmt.get("contract_format") != expected_cf:
            ctx.error("CONTRACT_FORMAT_MISMATCH", doc.path, "$.format.contract_format", f"expected {expected_cf!r}, got {fmt.get('contract_format')!r}")
        if expected_fv is not None and fmt.get("format_version") != expected_fv:
            ctx.error("FORMAT_VERSION_MISMATCH", doc.path, "$.format.format_version", f"local validator contract is {expected_fv!r}, got {fmt.get('format_version')!r}")

    identity = doc.data.get("identity")
    identity_contract = shape.get("identity")
    if not isinstance(identity, dict):
        ctx.error("IDENTITY_INVALID", doc.path, "$.identity", "identity must be an object")
    elif isinstance(identity_contract, dict):
        for field in identity_contract.get("required", []) if isinstance(identity_contract.get("required"), list) else []:
            if not isinstance(identity.get(field), str) or not identity.get(field):
                ctx.error("IDENTITY_REQUIRED_FIELD_INVALID", doc.path, f"$.identity.{field}", f"identity.{field} must be a non-empty string")

    scope = doc.data.get("scope")
    if not isinstance(scope, dict):
        ctx.error("SCOPE_INVALID", doc.path, "$.scope", "scope must be an object")
    else:
        for field in ("owns", "does_not_own"):
            if not isinstance(scope.get(field), list):
                ctx.error("SCOPE_FIELD_INVALID", doc.path, f"$.scope.{field}", f"scope.{field} must be an array")

    constraints = doc.data.get("constraints")
    if not isinstance(constraints, dict) or not isinstance(constraints.get("invariants"), list):
        ctx.error("CONSTRAINTS_INVALID", doc.path, "$.constraints.invariants", "constraints.invariants must be an array")
    else:
        for i, invariant in enumerate(constraints["invariants"]):
            if not isinstance(invariant, dict):
                ctx.error("INVARIANT_INVALID", doc.path, f"$.constraints.invariants[{i}]", "invariant must be an object")
                continue
            for field in ("id", "rule"):
                if not isinstance(invariant.get(field), str) or not invariant.get(field):
                    ctx.error("INVARIANT_FIELD_INVALID", doc.path, f"$.constraints.invariants[{i}].{field}", f"{field} must be non-empty")

    references = doc.data.get("references")
    if not isinstance(references, list):
        ctx.error("REFERENCES_INVALID", doc.path, "$.references", "references must be an array")
    else:
        for i, ref in enumerate(references):
            if not isinstance(ref, dict):
                ctx.error("REFERENCE_INVALID", doc.path, f"$.references[{i}]", "reference must be an object")
                continue
            for field in ("id", "target_ref", "purpose"):
                if not isinstance(ref.get(field), str) or not ref.get(field):
                    ctx.error("REFERENCE_FIELD_INVALID", doc.path, f"$.references[{i}].{field}", f"{field} must be non-empty")

    gaps = doc.data.get("gaps")
    if not isinstance(gaps, list):
        ctx.error("GAPS_INVALID", doc.path, "$.gaps", "gaps must be an array")

    prose = doc.data.get("prose")
    if not isinstance(prose, dict):
        ctx.error("PROSE_INVALID", doc.path, "$.prose", "prose must be an object")
    else:
        for field in ("summary", "notes"):
            if not isinstance(prose.get(field), str):
                ctx.error("PROSE_FIELD_INVALID", doc.path, f"$.prose.{field}", f"prose.{field} must be a string")

    if "specification_ref" not in doc.data:
        ctx.error("SPECIFICATION_REF_MISSING", doc.path, "$.specification_ref", "canonical interpretation provenance is required")


def collect_canonical_objects(docs: Sequence[ContractDocument], ctx: Context) -> Tuple[Dict[str, Tuple[str, ContractDocument, Dict[str, Any]]], Dict[str, str]]:
    objects: Dict[str, Tuple[str, ContractDocument, Dict[str, Any]]] = {}
    owners: Dict[str, str] = {}

    for doc in docs:
        entities = doc.data.get("entities")
        if not isinstance(entities, list):
            ctx.error("ENTITIES_INVALID", doc.path, "$.entities", "entities must be an array")
            continue
        for ei, entity in enumerate(entities):
            ep = f"$.entities[{ei}]"
            if not isinstance(entity, dict):
                ctx.error("ENTITY_INVALID", doc.path, ep, "entity must be an object")
                continue
            entity_id = entity.get("id")
            if not isinstance(entity_id, str) or not entity_id:
                ctx.error("ENTITY_ID_INVALID", doc.path, f"{ep}.id", "entity id must be non-empty")
                continue
            if entity_id in objects:
                ctx.error("CANONICAL_ID_DUPLICATE", doc.path, f"{ep}.id", f"canonical id {entity_id!r} already exists")
            else:
                objects[entity_id] = ("Entity", doc, entity)
            props = entity.get("properties")
            if not isinstance(props, list):
                ctx.error("ENTITY_PROPERTIES_INVALID", doc.path, f"{ep}.properties", "properties must be an array")
                continue
            for pi, prop in enumerate(props):
                pp = f"{ep}.properties[{pi}]"
                if not isinstance(prop, dict):
                    ctx.error("PROPERTY_INVALID", doc.path, pp, "property must be an object")
                    continue
                prop_id = prop.get("id")
                if not isinstance(prop_id, str) or not prop_id:
                    ctx.error("PROPERTY_ID_INVALID", doc.path, f"{pp}.id", "property id must be non-empty")
                    continue
                if prop_id in objects:
                    ctx.error("CANONICAL_ID_DUPLICATE", doc.path, f"{pp}.id", f"canonical id {prop_id!r} already exists")
                else:
                    objects[prop_id] = ("Property", doc, prop)
                    owners[prop_id] = entity_id
    return objects, owners


def type_matches(value: Any, declaration: Any) -> bool:
    if not isinstance(declaration, str):
        return True
    if declaration in {"string", "external_ref", "canonical_ref", "canonical_entity_ref", "canonical_property_ref", "canonical_or_external_ref", "interpretation_provenance_ref", "local_logic_primitive_set_ref"}:
        return isinstance(value, str) and bool(value)
    if declaration == "boolean":
        return isinstance(value, bool)
    if declaration in {"integer", "non_negative_integer"}:
        return isinstance(value, int) and not isinstance(value, bool) and (declaration != "non_negative_integer" or value >= 0)
    if declaration.startswith("array<"):
        return isinstance(value, list)
    if declaration.startswith("object") or declaration in {"map", "properties"}:
        return isinstance(value, dict)
    # Named semantic value forms are validated by their governing rules, not guessed here.
    return True


def validate_value_schema(prop: Dict[str, Any], rule: Dict[str, Any], doc: ContractDocument, path: str, ctx: Context) -> None:
    schema = rule.get("value_schema")
    value = prop.get("value")
    if not isinstance(value, dict):
        ctx.error("PROPERTY_VALUE_INVALID", doc.path, f"{path}.value", "Property.value must be an object")
        return
    if not isinstance(schema, dict):
        return
    required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
    optional = schema.get("optional", []) if isinstance(schema.get("optional"), list) else []
    fields = schema.get("fields") if isinstance(schema.get("fields"), dict) else {}
    for field in required:
        if field not in value:
            ctx.error("PROPERTY_VALUE_FIELD_MISSING", doc.path, f"{path}.value.{field}", f"required by {rule.get('id')}")
    for field in set(required) | set(optional):
        if field in value and field in fields and not type_matches(value[field], fields[field]):
            ctx.error("PROPERTY_VALUE_TYPE_MISMATCH", doc.path, f"{path}.value.{field}", f"value does not match declared type {fields[field]!r}")


def endpoint_constraint_matches(constraint: str, target_kind: str, target: Dict[str, Any], owner_entity: Optional[Dict[str, Any]]) -> bool:
    if constraint.startswith("entity_nodetype:"):
        return target_kind == "Entity" and target.get("entity_type_ref") == constraint.split(":", 1)[1]
    if constraint.startswith("property:"):
        return target_kind == "Property" and target.get("property_type_ref") == constraint.split(":", 1)[1]
    return False


def validate_reference_policy(
    ref_value: Any,
    policy: Mapping[str, Any],
    objects: Mapping[str, Tuple[str, ContractDocument, Dict[str, Any]]],
    file: Path,
    path: str,
    ctx: Context,
) -> None:
    refs = ref_value if isinstance(ref_value, list) else [ref_value]
    for i, ref in enumerate(refs):
        rp = f"{path}[{i}]" if isinstance(ref_value, list) else path
        if not isinstance(ref, str) or not ref:
            ctx.error("CANONICAL_REFERENCE_INVALID", file, rp, "reference must be a non-empty canonical id")
            continue
        resolved = objects.get(ref)
        if resolved is None:
            ctx.unready("CANONICAL_REFERENCE_UNRESOLVED", file, rp, f"canonical reference {ref!r} is unresolved in the input set")
            continue
        kind, _doc, target = resolved
        allowed_kinds = policy.get("allowed_canonical_kinds")
        if isinstance(allowed_kinds, list) and kind not in allowed_kinds:
            ctx.error("REFERENCE_KIND_INCOMPATIBLE", file, rp, f"{ref!r} resolves to {kind}, allowed={allowed_kinds}")
        allowed_types = policy.get("allowed_property_type_refs")
        if kind == "Property" and isinstance(allowed_types, list) and target.get("property_type_ref") not in allowed_types:
            ctx.error("REFERENCE_PROPERTY_TYPE_INCOMPATIBLE", file, rp, f"{ref!r} property_type_ref={target.get('property_type_ref')!r}, allowed={allowed_types}")
        allowed_nts = policy.get("allowed_nodetype_refs")
        if kind == "Entity" and isinstance(allowed_nts, list) and target.get("entity_type_ref") not in allowed_nts:
            ctx.error("REFERENCE_NODETYPE_INCOMPATIBLE", file, rp, f"{ref!r} entity_type_ref={target.get('entity_type_ref')!r}, allowed={allowed_nts}")


def validate_entities_and_properties(
    docs: Sequence[ContractDocument],
    standard: Standard,
    idx: Mapping[str, Any],
    objects: Mapping[str, Tuple[str, ContractDocument, Dict[str, Any]]],
    owners: Mapping[str, str],
    ctx: Context,
) -> None:
    nodetypes: Mapping[str, Dict[str, Any]] = idx["nodetypes"]
    cache: Dict[str, Dict[str, Any]] = {}

    for doc in docs:
        entities = doc.data.get("entities")
        if not isinstance(entities, list):
            continue
        for ei, entity in enumerate(entities):
            if not isinstance(entity, dict):
                continue
            ep = f"$.entities[{ei}]"
            for field in ("id", "name", "entity_type_ref", "status", "properties"):
                if field not in entity:
                    ctx.error("ENTITY_REQUIRED_FIELD_MISSING", doc.path, f"{ep}.{field}", f"missing Entity field {field!r}")
            nt_id = entity.get("entity_type_ref")
            if not isinstance(nt_id, str) or nt_id not in nodetypes:
                ctx.error("NODETYPE_UNRESOLVED", doc.path, f"{ep}.entity_type_ref", f"NodeType {nt_id!r} does not resolve")
                effective = None
            else:
                try:
                    effective = effective_nodetype(nt_id, nodetypes, cache)
                except Exception as exc:
                    raise RuntimeError(f"cannot resolve NodeType {nt_id}: {exc}") from exc

            props = entity.get("properties") if isinstance(entity.get("properties"), list) else []
            property_counts: Dict[str, int] = {}
            for pi, prop in enumerate(props):
                if not isinstance(prop, dict):
                    continue
                pp = f"{ep}.properties[{pi}]"
                for field in ("id", "property_type_ref", "ruleset_ref", "status", "value"):
                    if field not in prop:
                        ctx.error("PROPERTY_REQUIRED_FIELD_MISSING", doc.path, f"{pp}.{field}", f"missing Property field {field!r}")
                ptype = prop.get("property_type_ref")
                if isinstance(ptype, str):
                    property_counts[ptype] = property_counts.get(ptype, 0) + 1

                ruleset_ref = prop.get("ruleset_ref")
                rule: Optional[Dict[str, Any]] = None
                if ptype == "link":
                    if not isinstance(prop.get("value"), dict):
                        ctx.error("LINK_VALUE_INVALID", doc.path, f"{pp}.value", "Link value must be an object")
                        continue
                    link_type = prop["value"].get("link_type_ref")
                    matches = idx["link_rules_by_type"].get(link_type, []) if isinstance(link_type, str) else []
                    if len(matches) != 1:
                        ctx.error("LINK_TYPE_UNRESOLVED_OR_AMBIGUOUS", doc.path, f"{pp}.value.link_type_ref", f"link_type_ref {link_type!r} resolves to {len(matches)} Link Rulesets")
                    else:
                        rule = matches[0]
                        if ruleset_ref != rule.get("id"):
                            ctx.error("LINK_RULESET_REF_MISMATCH", doc.path, f"{pp}.ruleset_ref", f"expected {rule.get('id')!r} for link_type_ref {link_type!r}, got {ruleset_ref!r}")
                else:
                    matches = idx["prop_rules_by_type"].get(ptype, []) if isinstance(ptype, str) else []
                    if len(matches) != 1:
                        ctx.error("PROPERTY_TYPE_UNRESOLVED_OR_AMBIGUOUS", doc.path, f"{pp}.property_type_ref", f"property_type_ref {ptype!r} resolves to {len(matches)} Property Rulesets")
                    else:
                        rule = matches[0]
                        if ruleset_ref != rule.get("id"):
                            ctx.error("PROPERTY_RULESET_REF_MISMATCH", doc.path, f"{pp}.ruleset_ref", f"expected {rule.get('id')!r}, got {ruleset_ref!r}")

                if rule is not None:
                    validate_value_schema(prop, rule, doc, pp, ctx)
                    constraints = rule.get("reference_constraints")
                    value = prop.get("value")
                    if isinstance(constraints, dict) and isinstance(value, dict):
                        for field, policy in constraints.items():
                            if field in value and isinstance(policy, dict):
                                validate_reference_policy(value[field], policy, objects, doc.path, f"{pp}.value.{field}", ctx)

                if ptype == "link" and rule is not None and isinstance(prop.get("value"), dict):
                    validate_link(prop, rule, doc, pp, objects, owners, ctx)

            if effective is not None:
                for ptype in effective["required_property_types"]:
                    if property_counts.get(ptype, 0) < 1:
                        ctx.unready("REQUIRED_PROPERTY_MISSING", doc.path, ep, f"Entity {entity.get('id')!r} NodeType {nt_id!r} requires Property type {ptype!r}")
                for ptype, limits in effective["property_cardinality"].items():
                    count = property_counts.get(ptype, 0)
                    min_v = limits.get("min") if isinstance(limits, dict) else None
                    max_v = limits.get("max") if isinstance(limits, dict) else None
                    if isinstance(min_v, int) and count < min_v:
                        ctx.unready("PROPERTY_CARDINALITY_MIN_UNSATISFIED", doc.path, ep, f"Entity {entity.get('id')!r} has {count} {ptype!r} Properties, minimum is {min_v}")
                    if isinstance(max_v, int) and count > max_v:
                        ctx.error("PROPERTY_CARDINALITY_MAX_EXCEEDED", doc.path, ep, f"Entity {entity.get('id')!r} has {count} {ptype!r} Properties, maximum is {max_v}")

                validate_required_links(entity, effective["required_links"], doc, ep, objects, owners, idx, ctx)


def validate_link(
    prop: Dict[str, Any],
    rule: Dict[str, Any],
    doc: ContractDocument,
    path: str,
    objects: Mapping[str, Tuple[str, ContractDocument, Dict[str, Any]]],
    owners: Mapping[str, str],
    ctx: Context,
) -> None:
    value = prop.get("value")
    if not isinstance(value, dict):
        return
    for endpoint in ("parent_ref", "child_ref"):
        ref = value.get(endpoint)
        if not isinstance(ref, str) or not ref:
            ctx.error("LINK_ENDPOINT_INVALID", doc.path, f"{path}.value.{endpoint}", f"{endpoint} must be a canonical reference")
            continue
        resolved = objects.get(ref)
        if resolved is None:
            ctx.unready("LINK_ENDPOINT_UNRESOLVED", doc.path, f"{path}.value.{endpoint}", f"Link endpoint {ref!r} is unresolved")
            continue
        constraints_obj = rule.get("endpoint_constraints")
        constraints = constraints_obj.get(endpoint) if isinstance(constraints_obj, dict) else None
        if isinstance(constraints, list) and constraints:
            kind, _target_doc, target = resolved
            if not any(isinstance(c, str) and endpoint_constraint_matches(c, kind, target, None) for c in constraints):
                ctx.error("LINK_ENDPOINT_INCOMPATIBLE", doc.path, f"{path}.value.{endpoint}", f"endpoint {ref!r} does not satisfy {constraints}")


def validate_required_links(
    entity: Dict[str, Any],
    requirements: Sequence[Dict[str, Any]],
    doc: ContractDocument,
    path: str,
    objects: Mapping[str, Tuple[str, ContractDocument, Dict[str, Any]]],
    owners: Mapping[str, str],
    idx: Mapping[str, Any],
    ctx: Context,
) -> None:
    entity_id = entity.get("id")
    for req in requirements:
        req_id = req.get("id")
        ltype = req.get("link_type_ref")
        self_role = req.get("self_role")
        minimum = req.get("min", 0)
        maximum = req.get("max")
        matches = 0
        governing = idx["link_rules_by_type"].get(ltype, []) if isinstance(ltype, str) else []
        if len(governing) != 1:
            ctx.error("REQUIRED_LINK_RULESET_UNRESOLVED", doc.path, path, f"Required Link {req_id!r} link_type_ref {ltype!r} does not resolve exactly one Link Ruleset")
            continue
        rule = governing[0]
        semantic_roles = rule.get("semantic_roles") if isinstance(rule.get("semantic_roles"), dict) else {}
        endpoint_for_role = next((endpoint for endpoint, role in semantic_roles.items() if role == self_role), None)
        if endpoint_for_role not in {"parent_ref", "child_ref"}:
            ctx.error("REQUIRED_LINK_SELF_ROLE_UNRESOLVED", doc.path, path, f"Required Link {req_id!r} self_role {self_role!r} does not resolve")
            continue

        for _obj_id, (kind, _ldoc, candidate) in objects.items():
            if kind != "Property" or candidate.get("property_type_ref") != "link":
                continue
            value = candidate.get("value")
            if not isinstance(value, dict) or value.get("link_type_ref") != ltype:
                continue
            if value.get(endpoint_for_role) != entity_id:
                continue
            required_ref = value.get("required_link_ref")
            if not isinstance(required_ref, dict):
                continue
            if required_ref.get("entity_ref") == entity_id and required_ref.get("required_link_id") == req_id:
                matches += 1

        if isinstance(minimum, int) and matches < minimum:
            ctx.unready("REQUIRED_LINK_UNSATISFIED", doc.path, path, f"Entity {entity_id!r} Required Link {req_id!r} has {matches} satisfying Links; minimum is {minimum}")
        if isinstance(maximum, int) and matches > maximum:
            ctx.error("REQUIRED_LINK_MAX_EXCEEDED", doc.path, path, f"Entity {entity_id!r} Required Link {req_id!r} has {matches} satisfying Links; maximum is {maximum}")


def validate_top_level_references(
    docs: Sequence[ContractDocument],
    standard: Standard,
    objects: Mapping[str, Tuple[str, ContractDocument, Dict[str, Any]]],
    ctx: Context,
) -> None:
    known_spec_ids = {"CANONICAL_CONTRACT_FORMAT", "CW_NODETYPES", "CW_RULESETS"}
    for doc in docs:
        refs = doc.data.get("references")
        if not isinstance(refs, list):
            continue
        for i, ref in enumerate(refs):
            if not isinstance(ref, dict):
                continue
            target = ref.get("target_ref")
            if not isinstance(target, str):
                continue
            if target not in objects and target not in known_spec_ids:
                ctx.unready("TOP_LEVEL_REFERENCE_UNRESOLVED", doc.path, f"$.references[{i}].target_ref", f"target_ref {target!r} does not resolve in input set or local CW standard")


def outcome(ctx: Context) -> str:
    if any(f.severity == "ERROR" for f in ctx.findings):
        return "INVALID_MODEL"
    if any(f.severity == "UNREADY" for f in ctx.findings):
        return "UNREADY"
    return "READY"


def print_human(input_path: Path, spec_dir: Path, standard: Standard, docs: Sequence[ContractDocument], ctx: Context, result: str) -> None:
    print(f"CW artifact validator v{VALIDATOR_VERSION}")
    print(f"input: {input_path}")
    print(f"spec:  {spec_dir}")
    print(
        "standard: "
        f"CCF {standard.ccf.get('version')} / "
        f"NodeTypes {standard.nodetypes.get('version')} / "
        f"Rulesets {standard.rulesets.get('version')}"
    )
    print(f"documents: {len(docs)}")
    print()

    rank = {"ERROR": 0, "UNREADY": 1, "WARNING": 2}
    for finding in sorted(ctx.findings, key=lambda f: (rank.get(f.severity, 9), f.file, f.path, f.code)):
        print(f"{finding.severity:7} {finding.code}")
        print(f"        {Path(finding.file).name} {finding.path}")
        print(f"        {finding.message}")

    errors = sum(f.severity == "ERROR" for f in ctx.findings)
    unresolved = sum(f.severity == "UNREADY" for f in ctx.findings)
    warnings = sum(f.severity == "WARNING" for f in ctx.findings)
    print()
    print(f"RESULT: {result} ({errors} error(s), {unresolved} unresolved requirement(s), {warnings} warning(s))")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one CW JSON artifact or a directory artifact set against the local CW standard.")
    parser.add_argument("input", type=Path, help="CW .json file or directory containing CW JSON documents")
    parser.add_argument("--spec-dir", type=Path, default=None, help="override CW specification directory; default is repository root relative to this script")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--skip-spec-lint", action="store_true", help="skip cw_spec_lint.py self-integrity check of the CW standard")
    args = parser.parse_args()

    input_path = args.input.resolve()
    spec_dir = (args.spec_dir.resolve() if args.spec_dir else Path(__file__).resolve().parent.parent)
    ctx = Context()

    try:
        standard = load_standard(spec_dir)
    except Exception as exc:
        if args.json:
            print(json.dumps({"validator_version": VALIDATOR_VERSION, "result": "IMPLEMENTATION_FAILURE", "message": str(exc)}, indent=2))
        else:
            print(f"RESULT: IMPLEMENTATION_FAILURE\n{exc}", file=sys.stderr)
        return 2

    if not args.skip_spec_lint:
        ok, message = lint_standard(spec_dir)
        if not ok:
            if args.json:
                print(json.dumps({"validator_version": VALIDATOR_VERSION, "result": "INVALID_SPECIFICATION", "message": message}, indent=2))
            else:
                print(f"RESULT: INVALID_SPECIFICATION\n{message}", file=sys.stderr)
            return 1

    try:
        docs = load_input(input_path, ctx)
        if not docs and not ctx.findings:
            raise RuntimeError("no CW JSON documents loaded")
        idx = index_standard(standard)

        for doc in docs:
            validate_contract_shape(doc, standard, ctx)
        objects, owners = collect_canonical_objects(docs, ctx)
        validate_entities_and_properties(docs, standard, idx, objects, owners, ctx)
        validate_top_level_references(docs, standard, objects, ctx)

        result = outcome(ctx)
        if args.json:
            payload = {
                "validator_version": VALIDATOR_VERSION,
                "result": result,
                "input": str(input_path),
                "spec_dir": str(spec_dir),
                "standard": {
                    "ccf": standard.ccf.get("version"),
                    "nodetypes": standard.nodetypes.get("version"),
                    "rulesets": standard.rulesets.get("version"),
                },
                "documents": [str(doc.path) for doc in docs],
                "findings": [asdict(f) for f in ctx.findings],
                "summary": {
                    "errors": sum(f.severity == "ERROR" for f in ctx.findings),
                    "unready": sum(f.severity == "UNREADY" for f in ctx.findings),
                    "warnings": sum(f.severity == "WARNING" for f in ctx.findings),
                },
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_human(input_path, spec_dir, standard, docs, ctx, result)

        return 1 if result == "INVALID_MODEL" else 0
    except Exception as exc:
        if args.json:
            print(json.dumps({"validator_version": VALIDATOR_VERSION, "result": "IMPLEMENTATION_FAILURE", "message": str(exc)}, indent=2))
        else:
            print(f"RESULT: IMPLEMENTATION_FAILURE\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
