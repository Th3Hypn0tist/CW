#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "Examples" / "Ultralight_CMS" / "Model"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(msg: str) -> None:
    raise SystemExit("OWNER_LOCAL_REGRESSION_FAIL: " + msg)


def main() -> None:
    manifest = load(MODEL / "model.cw")
    entities: dict[str, dict[str, Any]] = {}
    files: dict[str, Path] = {}
    for shard in manifest.get("shards", []):
        path = MODEL / shard["artifact_ref"]
        entity = load(path)
        eid = entity.get("id")
        if not isinstance(eid, str) or eid in entities:
            fail(f"invalid/duplicate Entity.id {eid!r} in {path}")
        entities[eid] = entity
        files[eid] = path

    local: dict[str, dict[str, dict[str, Any]]] = {}
    repeated: dict[str, set[str]] = {}
    for eid, entity in entities.items():
        bucket: dict[str, dict[str, Any]] = {}
        for prop in entity.get("properties", []):
            pid = prop.get("id")
            if not isinstance(pid, str) or not pid:
                fail(f"invalid Property.id in {files[eid]}")
            if pid in bucket:
                fail(f"duplicate local Property.id {eid}/{pid}")
            if pid.startswith("MEMBERS::") or pid.startswith("ASSET::"):
                fail(f"owner-qualified role id remains: {eid}/{pid}")
            bucket[pid] = prop
            repeated.setdefault(pid, set()).add(eid)
        local[eid] = bucket

    if len(repeated.get("MEMBERS", set())) < 2:
        fail("MEMBERS does not demonstrate legal repeated owner-local id")
    if len(repeated.get("ASSET", set())) < 2:
        fail("ASSET does not demonstrate legal repeated owner-local id")

    def resolve(ref: Any, owner: str) -> tuple[str, str, dict[str, Any]] | None:
        if isinstance(ref, str):
            if ref in entities:
                return (ref, "Entity", entities[ref])
            prop = local.get(owner, {}).get(ref)
            return (owner, "Property", prop) if prop is not None else None
        if isinstance(ref, dict) and set(ref) == {"entity_ref", "property_ref"}:
            e = ref.get("entity_ref")
            p = ref.get("property_ref")
            if not isinstance(e, str) or not isinstance(p, str):
                return None
            prop = local.get(e, {}).get(p)
            return (e, "Property", prop) if prop is not None else None
        return None

    cross_addresses = 0
    for owner, entity in entities.items():
        for prop in entity.get("properties", []):
            pid = prop["id"]
            ptype = prop.get("property_type_ref")
            value = prop.get("value") if isinstance(prop.get("value"), dict) else {}

            if ptype == "function":
                for field in ("input_refs", "output_refs"):
                    for ref in value.get(field, []) if isinstance(value.get(field), list) else []:
                        if not isinstance(ref, str):
                            fail(f"Function {owner}/{pid} has non-local {field} ref {ref!r}")
                        target = resolve(ref, owner)
                        if target is None or target[1] != "Property":
                            fail(f"Function {owner}/{pid} unresolved owner-local {field} ref {ref!r}")

            if ptype == "link":
                for side in ("parent_ref", "child_ref"):
                    ref = value.get(side)
                    target = resolve(ref, owner)
                    if target is None:
                        fail(f"Link {owner}/{pid} unresolved {side}: {ref!r}")
                    if isinstance(ref, dict):
                        cross_addresses += int(ref.get("entity_ref") != owner)
                parent = resolve(value.get("parent_ref"), owner)
                child = resolve(value.get("child_ref"), owner)
                ltype = value.get("link_type_ref")
                if ltype == "event_cause":
                    if parent is None or parent[0] != owner or parent[1] != "Property" or parent[2].get("property_type_ref") != "function":
                        fail(f"event_cause {owner}/{pid} is not declared by its cause Function owner")
                    if child is None or child[1] != "Property" or child[2].get("property_type_ref") != "event":
                        fail(f"event_cause {owner}/{pid} child is not Event")
                elif ltype == "event_handler":
                    if parent is None or child is None or parent[0] != child[0] or parent[0] != owner:
                        fail(f"event_handler {owner}/{pid} crosses owner scope")
                    if parent[2].get("property_type_ref") != "event" or child[2].get("property_type_ref") != "function":
                        fail(f"event_handler {owner}/{pid} endpoint types invalid")
                elif ltype == "function_call":
                    if parent is None or child is None or parent[0] != owner or child[0] != owner:
                        fail(f"function_call {owner}/{pid} crosses Entity boundary")
                    if parent[2].get("property_type_ref") != "function" or child[2].get("property_type_ref") != "function":
                        fail(f"function_call {owner}/{pid} endpoint types invalid")

            def walk(node: Any) -> None:
                nonlocal cross_addresses
                if isinstance(node, dict):
                    if set(node) == {"entity_ref", "property_ref"}:
                        target = resolve(node, owner)
                        if target is None:
                            fail(f"unresolved structured Property address in {owner}/{pid}: {node!r}")
                        cross_addresses += int(node["entity_ref"] != owner)
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)
            walk(value)

    if cross_addresses == 0:
        fail("golden contains no explicit cross-Entity Property address")

    index = local["#FILE:index"]
    cause = index.get("LINK_OPEN_PAGE_CAUSES_RENDER_PAGE")
    if cause is None:
        fail("cross-Entity event_cause was not moved to #FILE:index declarer")
    renderer = local["#FILE:renderer"]
    if "LINK_OPEN_PAGE_CAUSES_RENDER_PAGE" in renderer:
        fail("renderer still declares index-owned event_cause")

    print("OWNER_LOCAL_REGRESSION_OK")
    print(f"entities={len(entities)} repeated_MEMBERS={len(repeated['MEMBERS'])} repeated_ASSET={len(repeated['ASSET'])} cross_addresses={cross_addresses}")


if __name__ == "__main__":
    main()
