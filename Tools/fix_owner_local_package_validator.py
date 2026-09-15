#!/usr/bin/env python3
from pathlib import Path

P = Path('linter/cw_package_validate.py')
s = P.read_text(encoding='utf-8')

s = s.replace(
'''def _walk_refs(value: Any, names: set[str]) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and isinstance(item, str):
                refs.append(item)
            refs.extend(_walk_refs(item, names))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_walk_refs(item, names))
    return refs
''',
'''def _property_key(owner: str, property_id: str) -> str:
    return owner + "\\0" + property_id


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
''')

s = s.replace(
'''        for prop in props:
            if not isinstance(prop, dict):
                f.error("PROPERTY_INVALID", path, entity_ref)
                continue
            prop_id = prop.get("id")
            if not isinstance(prop_id, str) or not prop_id:
                f.error("PROPERTY_ID_INVALID", path, entity_ref)
                continue
            if prop_id in properties or prop_id in entities:
                f.error("PROPERTY_ID_DUPLICATE", path, prop_id)
            properties[prop_id] = prop
            owners[prop_id] = entity_ref
            source_paths[prop_id] = path

    objects = set(entities) | set(properties)
''',
'''        local_ids: set[str] = set()
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
''')

s = s.replace('''    for prop_id, prop in properties.items():
        path = source_paths[prop_id]
''','''    for prop_key, prop in properties.items():
        prop_id = prop.get("id")
        owner = owners[prop_key]
        path = source_paths[prop_key]
''')

s = s.replace(
'''        elif prop_type == "data":
            schema_ref = value.get("schema_ref")
            if schema_ref is not None and (schema_ref not in properties or properties[schema_ref].get("property_type_ref") != "schema"):
                f.error("DATA_SCHEMA_REF_INVALID", path, f"{prop_id}: {schema_ref!r}")
''',
'''        elif prop_type == "data":
            schema_ref = value.get("schema_ref")
            target = _resolve_ref(schema_ref, owner, entities, properties) if schema_ref is not None else None
            if schema_ref is not None and (not isinstance(target, dict) or target.get("property_type_ref") != "schema"):
                f.error("DATA_SCHEMA_REF_INVALID", path, f"{prop_id}: {schema_ref!r}")
''')

s = s.replace(
'''            for ref in _walk_refs(definition, {"schema_ref", "item_schema_ref", "value_schema_ref"}):
                if ref not in properties or properties[ref].get("property_type_ref") != "schema":
                    f.error("SCHEMA_REF_INVALID", path, f"{prop_id}: {ref}")
            if schema_type == "map":
                if not isinstance(definition, dict) or not isinstance(definition.get("value_schema_ref"), str) or not definition.get("value_schema_ref"):
                    f.error("SCHEMA_MAP_VALUE_SCHEMA_MISSING", path, prop_id)
''',
'''            for ref in _walk_refs(definition, {"schema_ref", "item_schema_ref", "value_schema_ref"}):
                target = _resolve_ref(ref, owner, entities, properties)
                if not isinstance(target, dict) or target.get("property_type_ref") != "schema":
                    f.error("SCHEMA_REF_INVALID", path, f"{prop_id}: {ref!r}")
            if schema_type == "map":
                if not isinstance(definition, dict) or definition.get("value_schema_ref") is None:
                    f.error("SCHEMA_MAP_VALUE_SCHEMA_MISSING", path, prop_id)
''')

s = s.replace(
'''        elif prop_type == "function":
            for ref in [*(value.get("input_refs") or []), *(value.get("output_refs") or [])]:
                if ref not in properties:
                    f.error("FUNCTION_REF_UNRESOLVED", path, f"{prop_id}: {ref}")
            logic = value.get("logic")
''',
'''        elif prop_type == "function":
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
''')

s = s.replace('''                            properties=properties,
''','''                            properties=local_properties,
''',1)

s = s.replace(
'''            for field in ("parent_ref", "child_ref"):
                ref = value.get(field)
                if ref not in objects:
                    f.error("LINK_ENDPOINT_UNRESOLVED", path, f"{prop_id}.{field}: {ref!r}")
''',
'''            for field in ("parent_ref", "child_ref"):
                ref = value.get(field)
                if _resolve_ref(ref, owner, entities, properties) is None:
                    f.error("LINK_ENDPOINT_UNRESOLVED", path, f"{prop_id}.{field}: {ref!r}")
''')

s = s.replace(
'''                for finding in validate_event_dispatch_link(value, properties, entities):
''',
'''                local_properties = {
                    item.get("id"): item
                    for key, item in properties.items()
                    if owners.get(key) == owner and isinstance(item.get("id"), str)
                }
                for finding in validate_event_dispatch_link(value, local_properties, entities):
''')

s = s.replace('''            owner = owners[prop_id]
''','''            owner = owners[prop_key]
''')

s = s.replace(
'''    links = [p for p in properties.values() if p.get("property_type_ref") == "link"]

    for effect_id, effect in properties.items():
        if effect.get("property_type_ref") != "effect":
            continue
        effect_value = effect.get("value") if isinstance(effect.get("value"), dict) else {}
        target_values = []
        for link in links:
            link_value = link.get("value") if isinstance(link.get("value"), dict) else {}
            if link_value.get("link_type_ref") == "effect_target" and link_value.get("parent_ref") == effect_id:
                target_values.append(link_value)
        for finding in validate_effect_semantics(effect_value, target_values, dr):
            f.error(finding["code"], source_paths[effect_id], f"{effect_id}: {finding['message']}")

    for req_id, req in properties.items():
        if req.get("property_type_ref") != "required_link":
            continue
        path = source_paths[req_id]
        value = req.get("value") if isinstance(req.get("value"), dict) else {}
        owner = owners[req_id]
        self_endpoint = value.get("self_endpoint")
        matches = []
        for link in links:
            lv = link.get("value") if isinstance(link.get("value"), dict) else {}
            if lv.get("required_link_ref") != req_id:
                continue
            matches.append(link)
            if self_endpoint in {"parent_ref", "child_ref"} and lv.get(self_endpoint) != owner:
                f.error("REQUIRED_LINK_OWNER_ENDPOINT_MISMATCH", source_paths[link["id"]], f"{link['id']} -> {req_id}")
            if lv.get("link_type_ref") != value.get("link_type_ref"):
                f.error("REQUIRED_LINK_TYPE_MISMATCH", source_paths[link["id"]], f"{link['id']} -> {req_id}")
''',
'''    links = [(key, p) for key, p in properties.items() if p.get("property_type_ref") == "link"]

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
''')

P.write_text(s, encoding='utf-8')
print('owner-local package validator patch applied')
