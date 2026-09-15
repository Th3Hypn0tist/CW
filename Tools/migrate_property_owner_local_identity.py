#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "Examples" / "Ultralight_CMS"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def blob_sha(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], cwd=ROOT, text=True).strip()


def prop_addr(entity_ref: str, property_ref: str) -> dict[str, str]:
    return {"entity_ref": entity_ref, "property_ref": property_ref}


def migrate_ccf() -> Path:
    src = ROOT / "Canonical_Contract_Format_v2.4.3.json"
    dst = ROOT / "Canonical_Contract_Format_v2.5.0.json"
    ccf = load(src)
    ccf["version"] = "2.5.0"
    ccf["status"] = "unlocked"

    rules = ccf.get("fundamental_rules", [])
    for item in rules:
        if item.get("id") == "CF_ENTITY_PROPERTY_IDS_SHARE_CANONICAL_NAMESPACE":
            item["id"] = "CF_ENTITY_GLOBAL_PROPERTY_OWNER_LOCAL_IDENTITY"
            item["rule"] = (
                "Entity.id is canonical and model-global. Property.id is local to exactly one owning "
                "Entity.properties[] collection. Property canonical address is the ordered pair "
                "(owner Entity.id, local Property.id). Equal Property.id values in different Entities are valid."
            )
    rules.extend([
        {
            "id": "CF_PROPERTY_OWNERSHIP_BY_CONTAINMENT",
            "rule": "Containment in Entity.properties[] establishes Property ownership. Property.id MUST NOT duplicate owner Entity.id merely to manufacture model-global uniqueness."
        },
        {
            "id": "CF_CROSS_ENTITY_PROPERTY_ADDRESS_IS_EXPLICIT",
            "rule": "A Property owned by another Entity MUST be addressed explicitly with {entity_ref, property_ref}. A bare Property.id MUST NEVER trigger a Model-wide Property search."
        }
    ])

    prop_rule = ccf.get("canonical_core", {}).get("property")
    if isinstance(prop_rule, dict):
        prop_rule["rule"] = (
            "Property is the universal typed semantic attribute, relationship or behavior container attached to an Entity. "
            "Property.id is unique only inside its owning Entity.properties[] collection; containment establishes ownership. "
            "Its ruleset_ref is resolved in the containing artifact's pinned immutable specification closure."
        )

    ccf["property_address_model"] = {
        "identity": ["owner_entity_ref", "property_id"],
        "canonical_storage": {"owner_entity_ref": "implicit from Entity.properties[] containment", "property_id": "Property.id"},
        "local_reference": "bare Property.id only when field semantics explicitly define owner-local resolution",
        "cross_entity_address": {"entity_ref": "canonical Entity.id", "property_ref": "Property.id local to that Entity"},
        "synthetic_compound_id_forbidden": True,
        "model_wide_property_id_scan_forbidden": True
    }

    rr = ccf.get("reference_resolution", {})
    rr["identity_namespace"] = "entity_global_property_owner_local"
    rr["rule"] = (
        "Entity references resolve by model-global Entity.id. Bare Property ids resolve only inside an explicitly known owner Entity. "
        "Cross-Entity Property references use {entity_ref, property_ref}. Model-wide bare Property.id lookup is forbidden."
    )
    rr["applicable_context"] = (
        "Entity refs resolve in the model-global Entity namespace; Property refs resolve owner-locally or through an explicit Property address; "
        "specification-governed refs resolve only inside the pinned immutable specification closure."
    )

    ccf["identity_model"] = {
        "entity": {"identity": "Entity.id", "scope": "model_global", "unique": "complete Model closure"},
        "property": {
            "identity": ["owner Entity.id", "Property.id"],
            "scope": "owning Entity.properties[]",
            "same_id_across_different_entities": "valid",
            "duplicate_id_inside_same_entity": "invalid"
        },
        "rules": [
            "Entity.id MUST be unique across the complete Model closure.",
            "Property.id MUST be unique only inside the owning Entity.properties[] collection.",
            "Entity.id and Property.id do not share one identity namespace.",
            "A Property.id MAY equal an Entity.id without collision.",
            "A bare Property.id MUST NOT escape its explicitly known owner scope."
        ]
    }

    endpoint_refs = ccf.get("link_model", {}).get("endpoint_refs")
    if isinstance(endpoint_refs, dict):
        endpoint_refs["resolution"] = "Entity.id globally; Property owner-locally or by explicit {entity_ref, property_ref} address"
        endpoint_refs["rule"] = (
            "The applicable Link Ruleset constrains endpoint kinds and semantic roles. A cross-Entity Property endpoint MUST use an explicit Property address."
        )

    invariants = ccf.get("core_invariants", [])
    ccf["core_invariants"] = [
        "Entity identity is model-global; Property identity is owner-local and addressed canonically as owner Entity.id plus local Property.id."
        if item == "Entity and Property identities share one deterministic canonical identity namespace." else item
        for item in invariants
    ]

    classes = ccf.get("semantic_reference_resolution", {}).get("reference_classes")
    if isinstance(classes, dict):
        classes["canonical_identity_ref"] = (
            "Entity identities resolve model-globally. Property identities resolve relative to an explicitly known owner Entity; cross-Entity Property addresses carry entity_ref + property_ref."
        )

    operations = ccf.get("validator", {}).get("required_operations")
    if isinstance(operations, list):
        ccf["validator"]["required_operations"] = [
            "validate_entity_global_property_owner_local_identity" if op == "validate_entity_property_identity_namespace" else op
            for op in operations
        ]
        for op in ["validate_property_id_unique_per_owner", "validate_no_model_wide_bare_property_lookup", "validate_cross_entity_property_address"]:
            if op not in ccf["validator"]["required_operations"]:
                ccf["validator"]["required_operations"].append(op)

    dump(dst, ccf)
    return dst


def _find_ruleset(items: list[dict[str, Any]], ruleset_id: str) -> dict[str, Any]:
    for item in items:
        if item.get("id") == ruleset_id:
            return item
    raise KeyError(ruleset_id)


def migrate_root_dr() -> Path:
    src = ROOT / "CanonicalWireframe_Dependency_Rules_v3.14.0.json"
    dst = ROOT / "CanonicalWireframe_Dependency_Rules_v4.0.0.json"
    dr = load(src)
    dr["version"] = "4.0.0"
    principles = dr.setdefault("principles", [])
    principles.extend([
        "Entity identity is model-global; Property identity is owner-local.",
        "Bare Property ids resolve only inside an explicitly known owner Entity; cross-Entity Property addresses use {entity_ref, property_ref}.",
        "Function input/output and structured Function logic references are owner-local.",
        "Function-to-Function invocation may occur only when both Functions have the same owning Entity.",
        "Cross-Entity behavioral invocation is Event-mediated: Function -> event_cause -> Event -> event_handler -> Function.",
        "An event_handler Event and handler Function MUST have the same owning Entity."
    ])
    dr["canonical_reference_model"] = {
        "entity_ref": {"shape": "string", "scope": "model_global", "target": "Entity.id"},
        "local_property_ref": {"shape": "string", "scope": "explicitly known owner Entity", "target": "Property.id"},
        "property_address": {"shape": {"entity_ref": "canonical Entity.id", "property_ref": "local Property.id"}, "scope": "cross_entity"},
        "rules": [
            "No Model-wide index keyed only by Property.id is canonical.",
            "Equal Property.id values owned by different Entities are valid.",
            "A bare Property.id never causes a search in another Entity."
        ]
    }
    shared = dr.setdefault("shared_value_types", {})
    shared["property_address"] = {
        "required": ["entity_ref", "property_ref"],
        "fields": {"entity_ref": "canonical_entity_ref", "property_ref": "string"},
        "meaning": "Explicit address of one Property outside an already-known owner scope."
    }

    fn = _find_ruleset(dr.get("property_rulesets", []), "RULESET_FUNCTION")
    fields = fn.setdefault("value_schema", {}).setdefault("fields", {})
    fields["input_refs"] = "array<local_property_ref>"
    fields["output_refs"] = "array<local_property_ref>"
    fn["reference_constraints"] = {
        "input_refs": {"policy": "owner_local", "allowed_canonical_kinds": ["Property"], "owner": "containing Function owner Entity"},
        "output_refs": {"policy": "owner_local", "allowed_canonical_kinds": ["Property"], "owner": "containing Function owner Entity"}
    }
    fn["scope_rule"] = "Function input_refs/output_refs MUST resolve only inside the Entity that owns the Function Property."

    links = dr.get("link_rulesets", [])
    cause = _find_ruleset(links, "RULESET_LINK_EVENT_CAUSE")
    cause["property_owner"] = "cause_source"
    cause["owner_rule"] = "The event_cause Link Property is declared by the Entity that owns parent_ref/cause_source. This keeps Function emit cause_ref owner-local while child_ref may address an Event in another Entity."

    handler = _find_ruleset(links, "RULESET_LINK_EVENT_HANDLER")
    handler["scope_constraints"] = ["The Event parent_ref and Function child_ref MUST have the same canonical owning Entity."]

    call = _find_ruleset(links, "RULESET_LINK_FUNCTION_CALL")
    call["scope_constraints"] = ["caller_function and called_function MUST have the same canonical owning Entity."]
    call["dependency_derivation"] = {"dependency_forming": False, "reason": "Cross-Entity function_call is forbidden; same-owner calls do not derive Entity-level dependency."}
    call["reference_constraints"] = {
        "input_refs": {"policy": "owner_local", "allowed_canonical_kinds": ["Property"], "allowed_property_type_refs": ["data"], "owner": "caller Function owner Entity"},
        "output_refs": {"policy": "owner_local", "allowed_canonical_kinds": ["Property"], "allowed_property_type_refs": ["data"], "owner": "caller Function owner Entity"}
    }

    causality = dr.setdefault("causality", {})
    causality["function_call"] = "same-owner caller Function Property -> function_call -> same-owner called Function Property"
    causality["cross_entity_function_boundary"] = "Function -> event_cause -> Event -> event_handler -> Function"
    causality["direct_cross_entity_function_call"] = "forbidden"

    dump(dst, dr)
    return dst


def migrate_golden_dr() -> Path:
    path = GOLDEN / "Format" / "DR.json"
    dr = load(path)
    dr["version"] = "4.4.0-reference"
    principles = dr.setdefault("principles", [])
    principles = [p for p in principles if p != "function_call and logic op=call are forbidden."]
    principles.extend([
        "Property.id is owner-local; Property canonical address is owner Entity.id plus local Property.id.",
        "Bare Property ids never trigger Model-wide lookup.",
        "Function-to-Function calls are same-owner only; cross-Entity behavioral calls are Event-mediated."
    ])
    dr["principles"] = principles
    dr["reference_resolution"] = {
        "entity_ref": {"scope": "active Model closure", "syntax": "canonical Entity.id", "rule": "An Entity reference MUST resolve to exactly one active Entity.id in Model/."},
        "property_ref": {
            "scope": "owning Entity.properties[]",
            "syntax": "local Property.id",
            "identity_rule": "Property.id MUST be unique only inside one owning Entity.properties[] collection.",
            "resolution_rule": "A bare Property.id resolves only inside an explicitly known owner Entity. It MUST NEVER trigger Model-wide search.",
            "cross_entity_address": {"entity_ref": "canonical Entity.id", "property_ref": "Property.id local to that Entity"},
            "same_id_across_different_entities": "VALID",
            "duplicate_id_inside_same_entity": "INVALID"
        }
    }
    dynamic = dr.get("event_execution_model", {}).get("dynamic_dispatch")
    if isinstance(dynamic, dict):
        dynamic["selector_rule"] = "event_dispatch.selector_ref MUST resolve owner-locally to a Data Property. At dispatch time that Data MUST be READY and its runtime value MUST be a Property address object {entity_ref, property_ref}."
        dynamic["target_rule"] = "The selector value entity_ref MUST name an Entity inside the declared dispatch domain and property_ref MUST resolve inside that Entity to exactly one Event Property. Bare globally searched Event ids are forbidden."

    fim = dr.setdefault("function_interface_model", {})
    fim["input_refs"] = "Function.input_refs is the exact set of owner-local Property ids read by the Function's modeled logic."
    fim["output_refs"] = "Function.output_refs is the exact set of owner-local Property ids written/produced by the Function's modeled logic."
    fim["scope_rule"] = "Function input_refs/output_refs MUST resolve only inside the Entity that owns the Function. Cross-Entity data enters through explicit Link/Event semantics."

    for rs in dr.get("property_rulesets", []):
        if rs.get("id") == "RULESET_FUNCTION":
            cons = rs.setdefault("constraints", [])
            cons[:] = [c for c in cons if "canonical Property reference resolution" not in c]
            cons.insert(0, "input_refs and output_refs, when present, MUST resolve by bare Property.id only inside the Entity that owns the Function.")

    lrs = dr.setdefault("link_rulesets", [])
    for rs in lrs:
        if rs.get("id") == "RULESET_LINK_EVENT_HANDLER":
            rs["rule"] = "Event parent_ref and handler Function child_ref MUST resolve inside the same owning Entity."
        elif rs.get("id") == "RULESET_LINK_EVENT_CAUSE":
            rs["rule"] = "The Link Property MUST be owned by the Entity that owns parent_ref/cause Function. child_ref MAY be a structured cross-Entity Event address."
    if not any(rs.get("id") == "RULESET_LINK_FUNCTION_CALL" for rs in lrs):
        lrs.append({
            "id": "RULESET_LINK_FUNCTION_CALL",
            "property_type_ref": "link",
            "link_type_ref": "function_call",
            "parent_role": "caller Function",
            "child_role": "called Function",
            "direction": "caller -> called",
            "required_fields": ["input_refs", "output_refs"],
            "rule": "caller and called Function MUST be owned by the same Entity. input_refs/output_refs are owner-local Data Property ids. Cross-Entity function_call is INVALID."
        })

    primitive = dr.setdefault("logic_primitive_set", {})
    plist = primitive.setdefault("primitives", [])
    if "call" not in plist:
        plist.insert(plist.index("emit") if "emit" in plist else len(plist), "call")
    primitive["forbidden"] = [x for x in primitive.get("forbidden", []) if x != "call"]
    primitive.setdefault("semantics", {})["call"] = "Invoke one owner-local function_call Link whose parent/caller is the containing Function. Cross-Entity Function invocation is forbidden."
    primitive["semantics"]["emit"] = "Exactly one of cause_ref or dispatch_ref is required. cause_ref resolves owner-locally to an event_cause Link owned by the containing Function's Entity; its child Event may be cross-Entity by explicit Property address."

    link_types = dr.setdefault("link_types", [])
    if "function_call" not in link_types:
        link_types.append("function_call")
    dr["forbidden_link_types"] = [x for x in dr.get("forbidden_link_types", []) if x != "function_call"]
    dr.setdefault("causal_patterns", {})["same_owner_function_call"] = ["Function", "function_call", "Function"]
    dr["causal_patterns"]["function_boundary"] = ["Function", "event_cause", "Event", "event_handler", "Function"]
    dump(path, dr)
    return path


def migrate_golden_cw() -> Path:
    path = GOLDEN / "Format" / "CW.json"
    cw = load(path)
    cw["version"] = "2.1.0-reference"
    cw["property_address_model"] = {
        "entity_namespace": "model-global Entity.id",
        "property_namespace": "owner-local Property.id",
        "local_property_ref": "bare Property.id relative to explicitly known owner",
        "cross_entity_property_ref": {"entity_ref": "Entity.id", "property_ref": "local Property.id"},
        "flat_global_property_index": False,
        "synthetic_compound_property_id": False
    }
    cw.setdefault("model_closure", {}).setdefault("rules", []).extend([
        "Property.id uniqueness is validated per owning Entity, not across the Model closure.",
        "Package validators MUST NOT construct a flat Property index keyed only by Property.id."
    ])
    dump(path, cw)
    return path


def migrate_property_role_ids(entity: dict[str, Any]) -> None:
    for prop in entity.get("properties", []):
        if not isinstance(prop, dict):
            continue
        pid = prop.get("id")
        if isinstance(pid, str) and pid.startswith("MEMBERS::"):
            prop["id"] = "MEMBERS"
        elif isinstance(pid, str) and pid.startswith("ASSET::"):
            prop["id"] = "ASSET"


def migrate_golden_model() -> None:
    for path in GOLDEN.glob("Model/**/*.cw"):
        data = load(path)
        if path.name == "model.cw":
            continue
        migrate_property_role_ids(data)
        dump(path, data)

    def edit(path: str, fn) -> None:
        p = GOLDEN / "Model" / path
        data = load(p)
        fn(data)
        dump(p, data)

    def set_data_schema(entity: dict[str, Any], prop_id: str, owner: str, schema: str) -> None:
        for prop in entity["properties"]:
            if prop.get("id") == prop_id:
                prop["value"]["schema_ref"] = prop_addr(owner, schema)

    edit("FILE/content.cw", lambda e: set_data_schema(e, "DATA_CONTENT_COLLECTION", "#CTRCT:UltralightCMS:Content", "SCHEMA_CONTENT_COLLECTION"))
    edit("FILE/style.cw", lambda e: set_data_schema(e, "DATA_STYLE_STYLESHEET", "#CTRCT:UltralightCMS:Style", "SCHEMA_STYLE_SHEET"))

    def index_fix(e: dict[str, Any]) -> None:
        set_data_schema(e, "DATA_PAGE_REQUEST", "#CTRCT:UltralightCMS:PageRequest", "SCHEMA_PAGE_REQUEST")
        set_data_schema(e, "DATA_INDEX_DOCUMENT", "#CTRCT:UltralightCMS:RenderedDocument", "SCHEMA_RENDERED_DOCUMENT")
        props = e["properties"]
        if not any(p.get("id") == "LINK_OPEN_PAGE_CAUSES_RENDER_PAGE" for p in props):
            props.append({
                "id": "LINK_OPEN_PAGE_CAUSES_RENDER_PAGE", "property_type_ref": "link", "ruleset_ref": "RULESET_LINK_EVENT_CAUSE", "status": "unlocked",
                "value": {"link_type_ref": "event_cause", "parent_ref": "FUNCTION_OPEN_PAGE", "child_ref": prop_addr("#FILE:renderer", "EVENT_RENDER_PAGE"), "properties": {}}
            })
    edit("FILE/index.cw", index_fix)

    def renderer_fix(e: dict[str, Any]) -> None:
        set_data_schema(e, "DATA_SELECTED_CONTENT", "#CTRCT:UltralightCMS:Content", "SCHEMA_PAGE_CONTENT")
        set_data_schema(e, "DATA_RENDER_DRAFT", "#CTRCT:UltralightCMS:RenderedDocument", "SCHEMA_RENDERED_DOCUMENT")
        set_data_schema(e, "DATA_PUBLISH_DOCUMENT", "#CTRCT:UltralightCMS:RenderedDocument", "SCHEMA_RENDERED_DOCUMENT")
        e["properties"] = [p for p in e["properties"] if p.get("id") != "LINK_OPEN_PAGE_CAUSES_RENDER_PAGE"]
        external = {
            "LINK_RENDER_REQUEST_INPUT": prop_addr("#FILE:index", "DATA_PAGE_REQUEST"),
            "LINK_RENDER_CONTENT_INPUT": prop_addr("#FILE:content", "DATA_CONTENT_COLLECTION"),
            "LINK_RENDER_STYLE_INPUT": prop_addr("#FILE:style", "DATA_STYLE_STYLESHEET"),
            "LINK_RENDER_REQUEST_READY": prop_addr("#FILE:index", "DATA_PAGE_REQUEST"),
            "LINK_RENDER_CONTENT_READY": prop_addr("#FILE:content", "DATA_CONTENT_COLLECTION"),
            "LINK_RENDER_STYLE_READY": prop_addr("#FILE:style", "DATA_STYLE_STYLESHEET")
        }
        for p in e["properties"]:
            pid = p.get("id")
            if pid in external:
                p["value"]["parent_ref"] = external[pid]
            if pid == "LINK_PUBLISH_TARGET":
                p["value"]["child_ref"] = prop_addr("#FILE:index", "DATA_INDEX_DOCUMENT")
            if pid == "FUNCTION_RESOLVE_PAGE":
                p["value"]["input_refs"] = ["LINK_RENDER_REQUEST_INPUT", "LINK_RENDER_CONTENT_INPUT"]
                text = json.dumps(p["value"].get("logic", {}))
                text = text.replace('"DATA_PAGE_REQUEST"', '"LINK_RENDER_REQUEST_INPUT"').replace('"DATA_CONTENT_COLLECTION"', '"LINK_RENDER_CONTENT_INPUT"')
                p["value"]["logic"] = json.loads(text)
            if pid == "FUNCTION_COMPOSE_DOCUMENT":
                p["value"]["input_refs"] = ["DATA_SELECTED_CONTENT", "LINK_RENDER_STYLE_INPUT"]
                text = json.dumps(p["value"].get("logic", {})).replace('"DATA_STYLE_STYLESHEET"', '"LINK_RENDER_STYLE_INPUT"')
                p["value"]["logic"] = json.loads(text)
            if pid in {"LINK_COMPOSE_STYLE_INPUT", "LINK_COMPOSE_STYLE_READY"}:
                p["value"]["parent_ref"] = "LINK_RENDER_STYLE_INPUT"
    edit("FILE/renderer.cw", renderer_fix)

    def rendered_fix(e: dict[str, Any]) -> None:
        for p in e["properties"]:
            if p.get("id") == "SCHEMA_RENDERED_DOCUMENT":
                fields = p["value"]["definition"]["fields"]
                fields["content"]["schema_ref"] = prop_addr("#CTRCT:UltralightCMS:Content", "SCHEMA_PAGE_CONTENT")
                fields["style"]["schema_ref"] = prop_addr("#CTRCT:UltralightCMS:Style", "SCHEMA_STYLE_SHEET")
    edit("CTRCT/UltralightCMS/RenderedDocument.cw", rendered_fix)

    manifest = GOLDEN / "Model" / "model.cw"
    model = load(manifest)
    model["format"]["format_version"] = "2.5.0"
    model["identity"]["version"] = "2.1.0-reference"
    inv = model.get("constraints", {}).get("invariants", [])
    for item in inv:
        if item.get("id") == "GOLDEN_PROPERTY_ID_GLOBAL":
            item["id"] = "GOLDEN_PROPERTY_ID_OWNER_LOCAL"
            item["rule"] = "Entity.id is model-global. Property.id is unique only inside its owning Entity; Property canonical address is owner Entity.id plus local Property.id."
        elif item.get("id") == "GOLDEN_NO_FUNCTION_CALL":
            item["id"] = "GOLDEN_FUNCTION_BOUNDARY"
            item["rule"] = "function_call is permitted only between Functions owned by the same Entity. Cross-Entity behavioral invocation is Event-mediated."
        elif item.get("id") == "GOLDEN_CTRCT_CONTRACTS":
            item["rule"] = "Reusable CMS Schema Properties are owned by CTRCT/schema Entities. Cross-Entity Schema references use explicit {entity_ref, property_ref} addresses; same-owner Schema references may remain bare local ids."
    dump(manifest, model)


def migrate_golden_ccf(ccf_path: Path) -> Path:
    target = GOLDEN / "Format" / "CCF.json"
    target.write_text(ccf_path.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def migrate_golden_readme() -> None:
    path = GOLDEN / "README.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("CCF is the unchanged Canonical Contract Format 2.4.3.", "CCF 2.5.0 defines model-global Entity identity and owner-local Property identity.")
    text = re.sub(r"- Property identifiers are package-global.*?naming convention\.\n", "- Entity ids are model-global. Property ids are owner-local; cross-Entity Property references use explicit `{entity_ref, property_ref}` addresses. Bare Property ids never trigger Model-wide lookup.\n", text)
    text = text.replace("FILE Data Properties reference these package-global Schema ids.", "FILE Data Properties reference these Schema Properties through explicit owner-qualified Property addresses.")
    text = text.replace("`Function.input_refs` and `Function.output_refs` describe canonical Properties", "`Function.input_refs` and `Function.output_refs` describe owner-local Properties")
    marker = "`FUNCTION_OPEN_PAGE` therefore has empty `input_refs` and `output_refs`: it is intentionally a pure causal relay."
    if marker in text:
        text = text.replace(marker, marker + " Cross-Entity behavior crosses the Node boundary only through an Event; direct cross-Entity Function calls are forbidden, while same-Entity `function_call` remains valid.")
    path.write_text(text, encoding="utf-8")


def migrate_spec_set(ccf: Path, dr: Path) -> Path:
    old = ROOT / "spec_sets" / "CW_CORE_v1.1.0.json"
    new = ROOT / "spec_sets" / "CW_CORE_v1.2.0.json"
    spec = load(old)
    spec["version"] = "1.2.0"
    spec["ccf"] = {"path": "../" + ccf.name, "git_blob_sha": blob_sha(ccf)}
    spec["rulesets"] = {"path": "../" + dr.name, "git_blob_sha": blob_sha(dr)}
    spec["purpose"] = "Pin the immutable CW Core interpretation bundle with model-global Entity identity, owner-local Property identity, explicit cross-Entity Property addresses and Event-mediated cross-Entity Function boundaries."
    dump(new, spec)
    return new


def patch_validator() -> None:
    path = ROOT / "linter" / "cw_validate.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('VER = "2.4.1"', 'VER = "2.5.0"')
    text = text.replace('if description in {"logic_value", "logic_statement", "logic_representation", "required_link_ref"}:\n        return isinstance(value, dict)', 'if description in {"logic_value", "logic_statement", "logic_representation", "required_link_ref", "property_address"}:\n        return isinstance(value, dict)\n    if description == "canonical_ref":\n        return (isinstance(value, str) and bool(value)) or (isinstance(value, dict) and set(value) == {"entity_ref", "property_ref"} and all(isinstance(value[k], str) and value[k] for k in ("entity_ref", "property_ref")))\n    if description == "local_property_ref":\n        return isinstance(value, str) and bool(value)')
    text = text.replace('if description == "string" or description.endswith("_ref"):', 'if description == "string" or (description.endswith("_ref") and description != "canonical_ref"):')

    anchor = '\n\ndef endpoint_constraint_matches('
    helper = '''\n\ndef property_key(owner: str, property_id: str) -> str:\n    return owner + "\\0" + property_id\n\n\ndef resolve_ref(ref: Any, local_owner: str | None, objects: dict[str, tuple[str, dict, Path]]) -> tuple[str, dict, Path] | None:\n    if isinstance(ref, dict) and set(ref) == {"entity_ref", "property_ref"}:\n        entity_ref, property_ref = ref.get("entity_ref"), ref.get("property_ref")\n        if isinstance(entity_ref, str) and isinstance(property_ref, str):\n            return objects.get(property_key(entity_ref, property_ref))\n        return None\n    if not isinstance(ref, str) or not ref:\n        return None\n    entity = objects.get(ref)\n    if entity is not None and entity[0] == "Entity":\n        return entity\n    if local_owner is not None:\n        return objects.get(property_key(local_owner, ref))\n    return None\n\ndef owner_of_ref(ref: Any, local_owner: str | None, objects: dict[str, tuple[str, dict, Path]]) -> str | None:\n    if isinstance(ref, dict) and set(ref) == {"entity_ref", "property_ref"}:\n        return ref.get("entity_ref") if isinstance(ref.get("entity_ref"), str) else None\n    target = resolve_ref(ref, local_owner, objects)\n    if target is None:\n        return None\n    kind, value, _ = target\n    if kind == "Entity":\n        return value.get("id") if isinstance(value.get("id"), str) else None\n    return local_owner\n'''
    if helper.strip() not in text:
        text = text.replace(anchor, helper + anchor)

    text = text.replace('    target = objects.get(endpoint_ref)\n', '    target = resolve_ref(endpoint_ref, None, objects)\n')
    text = text.replace('        target = objects.get(ref)\n', '        target = resolve_ref(ref, None, objects)\n')

    old_index = '''        objects: dict[str, tuple[str, dict, Path]] = {}\n        owners: dict[str, str] = {}\n'''
    text = text.replace(old_index, '        objects: dict[str, tuple[str, dict, Path]] = {}\n')
    text = text.replace('                    objects[entity_id] = ("Entity", entity, file)\n                    owners[entity_id] = entity_id\n', '                    objects[entity_id] = ("Entity", entity, file)\n')
    old_prop = '''                    if isinstance(property_id, str):\n                        if property_id in objects:\n                            c.e("CANONICAL_ID_DUPLICATE", file, property_path + ".id", property_id)\n                        objects[property_id] = ("Property", prop, file)\n                        if isinstance(entity_id, str):\n                            owners[property_id] = entity_id\n'''
    new_prop = '''                    if isinstance(property_id, str) and isinstance(entity_id, str):\n                        key = property_key(entity_id, property_id)\n                        if key in objects:\n                            c.e("PROPERTY_ID_DUPLICATE_IN_OWNER", file, property_path + ".id", property_id)\n                        objects[key] = ("Property", prop, file)\n'''
    text = text.replace(old_prop, new_prop)

    # Validation loop: owner-aware resolution for Property fields and Link endpoints.
    text = text.replace('                entity_path = f"$.entities[{entity_index}]"\n                nodetype = entity.get("entity_type_ref")', '                entity_path = f"$.entities[{entity_index}]"\n                owner_id = entity.get("id") if isinstance(entity.get("id"), str) else None\n                nodetype = entity.get("entity_type_ref")')
    text = text.replace('                            target = objects.get(ref)\n', '                            target = resolve_ref(ref, owner_id, objects)\n')
    text = text.replace('                            topology = objects.get(relation)\n', '                            topology = resolve_ref(relation, None, objects)\n')
    text = text.replace('                            target = objects.get(ref)\n                            if target is None:\n                                c.u("LINK_ENDPOINT_UNRESOLVED"', '                            target = resolve_ref(ref, owner_id, objects)\n                            if target is None:\n                                c.u("LINK_ENDPOINT_UNRESOLVED"')

    scope_insert = '''                        # Owner-scope invariants.\n                        parent_owner = owner_of_ref(value.get("parent_ref"), owner_id, objects)\n                        child_owner = owner_of_ref(value.get("child_ref"), owner_id, objects)\n                        if ruleset_ref == "RULESET_LINK_EVENT_CAUSE" and parent_owner is not None and owner_id != parent_owner:\n                            c.e("EVENT_CAUSE_DECLARER_SCOPE_INVALID", file, property_path, "event_cause must be owned by cause Function owner Entity")\n                        if ruleset_ref == "RULESET_LINK_EVENT_HANDLER" and parent_owner is not None and child_owner is not None and parent_owner != child_owner:\n                            c.e("EVENT_HANDLER_OWNER_SCOPE_INVALID", file, property_path, "Event and handler Function must share one owner Entity")\n                        if ruleset_ref == "RULESET_LINK_FUNCTION_CALL" and parent_owner is not None and child_owner is not None and parent_owner != child_owner:\n                            c.e("FUNCTION_CALL_CROSS_OWNER_FORBIDDEN", file, property_path, "cross-Entity Function call must use Event boundary")\n'''
    marker = '                        endpoint_constraints = ruleset.get("endpoint_constraints", {}) if isinstance(ruleset.get("endpoint_constraints"), dict) else {}\n'
    if scope_insert.strip() not in text:
        text = text.replace(marker, scope_insert + marker)

    # Function refs must be bare owner-local Property ids.
    fn_insert = '''                    if property_type == "function":\n                        for field in ("input_refs", "output_refs"):\n                            refs = value.get(field, [])\n                            if isinstance(refs, list):\n                                for ref_index, ref in enumerate(refs):\n                                    ref_path = property_path + f".value.{field}[{ref_index}]"\n                                    if not isinstance(ref, str):\n                                        c.e("FUNCTION_REF_NOT_OWNER_LOCAL", file, ref_path, "Function I/O requires bare owner-local Property.id")\n                                        continue\n                                    target = resolve_ref(ref, owner_id, objects)\n                                    if target is None or target[0] != "Property":\n                                        c.u("FUNCTION_LOCAL_REF_UNRESOLVED", file, ref_path, repr(ref))\n'''
    marker2 = '                    if property_type == "function" and isinstance(value.get("logic"), dict):\n'
    if fn_insert.strip() not in text:
        text = text.replace(marker2, fn_insert + marker2)

    path.write_text(text, encoding="utf-8")


def add_regression_fixture() -> None:
    path = ROOT / "tests" / "fixtures" / "property_owner_local_identity.json"
    fixture = {
        "valid_repeated_local_id": [
            {"id": "#A:One", "properties": [{"id": "MEMBERS"}]},
            {"id": "#A:Two", "properties": [{"id": "MEMBERS"}]}
        ],
        "invalid_duplicate_same_owner": {"id": "#A:One", "properties": [{"id": "MEMBERS"}, {"id": "MEMBERS"}]},
        "valid_cross_entity_address": {"entity_ref": "#A:Two", "property_ref": "MEMBERS"},
        "forbidden": ["Model-wide bare Property.id scan", "owner-qualified text encoded into Property.id", "cross-Entity function_call"]
    }
    dump(path, fixture)


def main() -> None:
    ccf = migrate_ccf()
    dr = migrate_root_dr()
    migrate_golden_ccf(ccf)
    migrate_golden_dr()
    migrate_golden_cw()
    migrate_golden_model()
    migrate_golden_readme()
    patch_validator()
    add_regression_fixture()
    migrate_spec_set(ccf, dr)
    # Sanity: every generated JSON parses.
    for path in [ccf, dr, GOLDEN / "Format" / "CCF.json", GOLDEN / "Format" / "DR.json", GOLDEN / "Format" / "CW.json", ROOT / "spec_sets" / "CW_CORE_v1.2.0.json"]:
        load(path)
    for path in GOLDEN.glob("Model/**/*.cw"):
        load(path)
    print("property owner-local identity migration generated successfully")


if __name__ == "__main__":
    main()
