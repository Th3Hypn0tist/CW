#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NT_SOURCE = ROOT / "CanonicalWireframe_NodeTypes_v1.15.1.json"
NT_TARGET = ROOT / "CanonicalWireframe_NodeTypes_v1.16.0.json"
RS_SOURCE = ROOT / "CanonicalWireframe_Dependency_Rules_v3.11.2.json"
RS_TARGET = ROOT / "CanonicalWireframe_Dependency_Rules_v3.12.0.json"
HISTORY = ROOT / "History"

COMMON_LINK_VALUE_SCHEMA = {
    "required": ["link_type_ref", "parent_ref", "child_ref", "properties"],
    "optional": ["required_link_ref"],
    "fields": {
        "link_type_ref": "string",
        "parent_ref": "canonical_ref",
        "child_ref": "canonical_ref",
        "properties": "object",
        "required_link_ref": "required_link_ref|null",
    },
}


def load(path: Path, expected_id: str, expected_version: str) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if data.get("id") != expected_id or data.get("version") != expected_version:
        raise SystemExit(f"{path.name}: expected {expected_id} {expected_version}")
    return text, data


def ensure_absent(items: list[dict], ids: set[str], field: str = "id") -> None:
    existing = {item.get(field) for item in items if isinstance(item, dict)}
    dup = sorted(ids & existing)
    if dup:
        raise SystemExit(f"new ids already exist: {dup}")


def archive(path: Path, text: str) -> None:
    HISTORY.mkdir(parents=True, exist_ok=True)
    dst = HISTORY / path.name
    if dst.exists():
        if dst.read_text(encoding="utf-8") != text:
            raise SystemExit(f"history collision with different content: {dst}")
    else:
        dst.write_text(text, encoding="utf-8")


def required_link(req_id: str, link_type_ref: str, self_role: str) -> dict:
    return {
        "id": req_id,
        "link_type_ref": link_type_ref,
        "self_role": self_role,
        "min": 1,
        "description": "At least one canonical target relation is required for readiness.",
    }


def main() -> None:
    if NT_TARGET.exists() or RS_TARGET.exists():
        raise SystemExit("target specification already exists")

    nt_text, nt = load(NT_SOURCE, "CW_NODETYPES", "1.15.1")
    rs_text, rs = load(RS_SOURCE, "CW_RULESETS", "3.11.2")

    nodetypes = nt.get("nodetypes")
    if not isinstance(nodetypes, list):
        raise SystemExit("CW_NODETYPES.nodetypes missing")

    ensure_absent(nodetypes, {"topology_entity", "file", "abs", "doc", "ctrct"})

    shared_owned = ["event", "effect", "data", "function", "file", "link"]

    nodetypes.extend([
        {
            "id": "topology_entity",
            "name": "Topology Entity",
            "extends": ["generic"],
            "required_property_types": [],
            "owned_property_types": shared_owned,
            "description": "Shared canonical Entity/Node/Property template for FILE, ABS, DOC and CTRCT topology entities.",
            "constraints": [
                "FILE, ABS, DOC and CTRCT use one canonical Entity/Property model and one Node projection principle.",
                "The Entity entity_type_ref is NodeType authority; consumers MUST NOT infer NodeType semantics from identity prefix, filename, extension, directory or rendering.",
                "Owned Property types are structural expectations and are not a closed allow-list.",
                "All machine-significant relations remain canonical Link Properties governed by CW_RULESETS."
            ]
        },
        {
            "id": "file",
            "name": "File",
            "extends": ["topology_entity"],
            "required_property_types": [],
            "owned_property_types": shared_owned,
            "description": "Canonical Entity for one accepted implementation source file; provides the master implementation topology.",
            "constraints": [
                "One accepted implementation source file maps to one canonical File Entity identity.",
                "Source-language suffix and physical file extension do not create a second canonical identity.",
                "Function, Event, Data, Effect and Link Properties remain owned by the canonical File Entity when modeled.",
                "FILE is the master implementation topology; other core topology entities reference File or Abstraction identities rather than copying their semantic definitions."
            ]
        },
        {
            "id": "abs",
            "name": "Abstraction",
            "extends": ["topology_entity"],
            "required_property_types": [],
            "owned_property_types": shared_owned,
            "required_links": [required_link("ABS_MEMBER_TARGET", "abstraction_member", "abstraction")],
            "description": "Canonical abstraction Entity over already canonical File or Abstraction identities.",
            "constraints": [
                "Abstraction membership references canonical File or Abstraction Entities and never duplicates their identities or semantic definitions.",
                "The governing abstraction_member Link Ruleset defines membership endpoint semantics and canonical Link Property placement.",
                "Existing Required Link input projection and Output/Binding mechanisms remain unchanged by this NodeType."
            ]
        },
        {
            "id": "doc",
            "name": "Document",
            "extends": ["topology_entity"],
            "required_property_types": ["file"],
            "owned_property_types": shared_owned,
            "property_cardinality": {"file": {"min": 1, "max": 1}},
            "required_links": [required_link("DOC_TARGET", "documentation_target", "document")],
            "description": "Canonical document Entity whose physical readable representation is carried by its File Property and whose semantic target is a canonical File or Abstraction Entity.",
            "constraints": [
                "The File Property identifies the physical document representation; no .cw extension is required.",
                "Document representation format is open and may be any supported readable type, including Markdown, text, HTML, JSON or PDF.",
                "Filename, extension, path and directory placement do not define canonical document semantics or NodeType.",
                "A Document references canonical File or Abstraction targets and does not duplicate the target semantic definition.",
                "Additional canonical Links, including ownership or other domain relations, remain permitted when their governing Rulesets allow them."
            ]
        },
        {
            "id": "ctrct",
            "name": "Contract",
            "extends": ["topology_entity"],
            "required_property_types": [],
            "owned_property_types": shared_owned,
            "required_links": [required_link("CTRCT_TARGET", "contract_target", "contract")],
            "description": "Canonical contract Entity concerning a canonical File or Abstraction target.",
            "constraints": [
                "A Contract references canonical File or Abstraction Entities and does not become an alternate definition of them.",
                "Contract semantics are expressed through canonical Properties and Links governed by the pinned specification closure."
            ]
        },
    ])

    nt_rules = nt.get("rules")
    if not isinstance(nt_rules, list):
        raise SystemExit("CW_NODETYPES.rules missing")
    nt_rules.extend([
        "FILE, ABS, DOC and CTRCT are canonical Entity NodeTypes sharing one topology_entity base and one canonical Entity/Property model.",
        "FILE provides the master implementation topology; ABS, DOC and CTRCT reference canonical FILE or ABS targets and MUST NOT duplicate the referenced semantic definitions.",
        "DOC physical representation is format-open; a file Property identifies the representation and no .cw extension is required.",
        "Identity-family prefixes such as #FILE, #ABS, #DOC and #CTRCT are canonical identity conventions, but NodeType semantics are resolved from Entity.entity_type_ref inside the pinned specification closure and MUST NOT be inferred from the prefix."
    ])

    nt["core_topology_model"] = {
        "principle": "One truth. Many topologies. No duplicate truth.",
        "shared_nodetype_ref": "topology_entity",
        "master_implementation_nodetype_ref": "file",
        "reference_nodetype_refs": ["abs", "doc", "ctrct"],
        "canonical_identity_families": ["#FILE", "#ABS", "#DOC", "#CTRCT"],
        "type_authority": "Entity.entity_type_ref",
        "prefix_inference_forbidden": True,
        "reference_targets": {
            "abs": ["file", "abs"],
            "doc": ["file", "abs"],
            "ctrct": ["file", "abs"],
        },
        "serialization": {
            "monolithic_allowed": True,
            "sharded_allowed": True,
            "semantic_equivalence_required": True,
            "shard_roots": {"file": "FILE/", "abs": "ABS/", "doc": "DOC/", "ctrct": "CTRCT/"},
            "doc_extension_fixed": False,
            "path_semantic_authority": False,
        },
    }

    nt["version"] = "1.16.0"

    link_rulesets = rs.get("link_rulesets")
    if not isinstance(link_rulesets, list):
        raise SystemExit("CW_RULESETS.link_rulesets missing")
    ensure_absent(link_rulesets, {
        "RULESET_LINK_ABSTRACTION_MEMBER",
        "RULESET_LINK_DOCUMENTATION_TARGET",
        "RULESET_LINK_CONTRACT_TARGET",
    })
    existing_link_types = {x.get("link_type_ref") for x in link_rulesets if isinstance(x, dict)}
    for link_type in ("abstraction_member", "documentation_target", "contract_target"):
        if link_type in existing_link_types:
            raise SystemExit(f"link_type_ref already exists: {link_type}")

    link_rulesets.extend([
        {
            "id": "RULESET_LINK_ABSTRACTION_MEMBER",
            "property_type_ref": "link",
            "link_type_ref": "abstraction_member",
            "value_schema": COMMON_LINK_VALUE_SCHEMA,
            "semantic_roles": {"parent_ref": "member", "child_ref": "abstraction"},
            "property_owner": "abstraction",
            "unresolved_impact": {"from_role": "member", "to_role": "abstraction"},
            "endpoint_constraints": {
                "parent_ref": ["entity_nodetype:file", "entity_nodetype:abs"],
                "child_ref": ["entity_nodetype:abs"],
            },
            "constraints": [
                "The member endpoint references an already canonical File or Abstraction Entity.",
                "Membership creates no duplicate canonical identity or copied semantic definition.",
                "Abstraction membership is canonical Link semantics and MUST NOT be inferred from geometry, directory placement or renderer containment."
            ]
        },
        {
            "id": "RULESET_LINK_DOCUMENTATION_TARGET",
            "property_type_ref": "link",
            "link_type_ref": "documentation_target",
            "value_schema": COMMON_LINK_VALUE_SCHEMA,
            "semantic_roles": {"parent_ref": "documented_target", "child_ref": "document"},
            "property_owner": "document",
            "unresolved_impact": {"from_role": "documented_target", "to_role": "document"},
            "endpoint_constraints": {
                "parent_ref": ["entity_nodetype:file", "entity_nodetype:abs"],
                "child_ref": ["entity_nodetype:doc"],
            },
            "constraints": [
                "A Document target is a canonical File or Abstraction Entity.",
                "The Document remains an independent canonical Entity while the target definition remains authoritative for the referenced target.",
                "Additional ownership, dependency, authority or other canonical Links may coexist when valid under their own Rulesets."
            ]
        },
        {
            "id": "RULESET_LINK_CONTRACT_TARGET",
            "property_type_ref": "link",
            "link_type_ref": "contract_target",
            "value_schema": COMMON_LINK_VALUE_SCHEMA,
            "semantic_roles": {"parent_ref": "contract_target", "child_ref": "contract"},
            "property_owner": "contract",
            "unresolved_impact": {"from_role": "contract_target", "to_role": "contract"},
            "endpoint_constraints": {
                "parent_ref": ["entity_nodetype:file", "entity_nodetype:abs"],
                "child_ref": ["entity_nodetype:ctrct"],
            },
            "constraints": [
                "A Contract target is a canonical File or Abstraction Entity.",
                "A Contract does not replace, clone or become an alternate canonical definition of its target.",
                "Contract-specific obligations and constraints remain explicit canonical semantics rather than inferred from filenames, prose location or directory structure."
            ]
        },
    ])

    principles = rs.get("principles")
    if not isinstance(principles, list):
        raise SystemExit("CW_RULESETS.principles missing")
    principles.extend([
        "FILE is the master implementation topology; ABS, DOC and CTRCT participate in the same canonical graph by explicit canonical references and Links rather than copied semantic definitions.",
        "abstraction_member, documentation_target and contract_target are canonical Link specializations; their endpoint roles, compatibility and Property placement are Ruleset authority.",
        "DOC physical representation format is not canonical semantic authority; the existing File Property may identify a readable representation without imposing a .cw extension.",
        "Identity prefixes, paths, filenames, extensions and directory structure MUST NOT be used to infer missing Entity type or Link semantics."
    ])

    rs["core_topology_links"] = {
        "principle": "One truth. Many topologies. No duplicate truth.",
        "master_implementation_nodetype_ref": "file",
        "links": {
            "abstraction_member": {
                "source_nodetype_refs": ["file", "abs"],
                "target_nodetype_ref": "abs",
                "owner_role": "abstraction",
            },
            "documentation_target": {
                "source_nodetype_refs": ["file", "abs"],
                "target_nodetype_ref": "doc",
                "owner_role": "document",
            },
            "contract_target": {
                "source_nodetype_refs": ["file", "abs"],
                "target_nodetype_ref": "ctrct",
                "owner_role": "contract",
            },
        },
        "closed_link_vocabulary": False,
    }

    rs["version"] = "3.12.0"

    archive(NT_SOURCE, nt_text)
    archive(RS_SOURCE, rs_text)

    NT_TARGET.write_text(json.dumps(nt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RS_TARGET.write_text(json.dumps(rs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    NT_SOURCE.unlink()
    RS_SOURCE.unlink()

    print(f"archived: History/{NT_SOURCE.name}")
    print(f"archived: History/{RS_SOURCE.name}")
    print(f"created:  {NT_TARGET.name}")
    print(f"created:  {RS_TARGET.name}")


if __name__ == "__main__":
    main()
