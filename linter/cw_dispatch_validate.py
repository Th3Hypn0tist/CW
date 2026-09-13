from __future__ import annotations

from typing import Any


def _members_property(entity: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    matches = [
        prop for prop in entity.get("properties", [])
        if isinstance(prop, dict) and prop.get("property_type_ref") == "members"
    ]
    if len(matches) != 1:
        return None, "DISPATCH_DOMAIN_MEMBERS_INVALID"
    return matches[0], None


def validate_event_dispatch_link(
    value: dict[str, Any],
    properties: dict[str, dict[str, Any]],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    selector_ref = value.get("selector_ref")
    selector = properties.get(selector_ref) if isinstance(selector_ref, str) else None
    if not isinstance(selector, dict) or selector.get("property_type_ref") != "data":
        findings.append({
            "code": "EVENT_DISPATCH_SELECTOR_INVALID",
            "message": "selector_ref must resolve to one Data Property",
        })

    domain_ref = value.get("child_ref")
    domain = entities.get(domain_ref) if isinstance(domain_ref, str) else None
    if not isinstance(domain, dict):
        findings.append({
            "code": "EVENT_DISPATCH_DOMAIN_INVALID",
            "message": "child_ref must resolve to one dispatch domain Entity",
        })
    else:
        _, error = _members_property(domain)
        if error:
            findings.append({
                "code": error,
                "message": "dispatch domain must own exactly one members Property",
            })
    return findings


def resolve_event_dispatch(
    *,
    dispatch_value: dict[str, Any],
    selector_state: str,
    selector_value: Any,
    properties: dict[str, dict[str, Any]],
    owners: dict[str, str],
    entities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    structural = validate_event_dispatch_link(dispatch_value, properties, entities)
    if structural:
        return {"result": None, "state": "INVALID", "finding": structural[0]}

    if selector_state != "READY":
        return {
            "result": None,
            "state": "INVALID",
            "finding": {
                "code": "EVENT_DISPATCH_SELECTOR_NOT_READY",
                "message": "dynamic Event dispatch requires READY selector Data",
            },
        }
    if not isinstance(selector_value, str) or not selector_value:
        return {
            "result": None,
            "state": "INVALID",
            "finding": {
                "code": "EVENT_DISPATCH_SELECTOR_VALUE_INVALID",
                "message": "selector runtime value must be an exact canonical Event Property.id string",
            },
        }

    target = properties.get(selector_value)
    if not isinstance(target, dict):
        return {
            "result": None,
            "state": "INVALID",
            "finding": {
                "code": "EVENT_DISPATCH_TARGET_UNRESOLVED",
                "message": f"selector does not resolve an exact Property.id: {selector_value}",
            },
        }
    if target.get("property_type_ref") != "event":
        return {
            "result": None,
            "state": "INVALID",
            "finding": {
                "code": "EVENT_DISPATCH_TARGET_NOT_EVENT",
                "message": "selector target must be an Event Property",
            },
        }

    owner = owners.get(selector_value)
    domain = entities[dispatch_value["child_ref"]]
    members, _ = _members_property(domain)
    member_value = members.get("value") if isinstance(members, dict) else None
    member_refs = member_value.get("member_refs") if isinstance(member_value, dict) else None
    allowed = set(member_refs) if isinstance(member_refs, list) else set()
    if owner not in allowed:
        return {
            "result": None,
            "state": "INVALID",
            "finding": {
                "code": "EVENT_DISPATCH_TARGET_OUTSIDE_DOMAIN",
                "message": "selected Event owner is not a direct member of the dispatch domain",
            },
        }

    return {"result": selector_value, "state": "READY", "finding": None}


def validate_emit_statement(
    statement: dict[str, Any],
    *,
    containing_function_ref: str,
    properties: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    cause_ref = statement.get("cause_ref")
    dispatch_ref = statement.get("dispatch_ref")
    present = int(isinstance(cause_ref, str) and bool(cause_ref)) + int(
        isinstance(dispatch_ref, str) and bool(dispatch_ref)
    )
    if present != 1:
        return [{
            "code": "EMIT_ROUTE_CARDINALITY_INVALID",
            "message": "emit requires exactly one of cause_ref or dispatch_ref",
        }]

    ref = cause_ref if isinstance(cause_ref, str) and cause_ref else dispatch_ref
    expected_type = "event_cause" if ref == cause_ref else "event_dispatch"
    link = properties.get(ref)
    link_value = link.get("value") if isinstance(link, dict) and isinstance(link.get("value"), dict) else {}
    if not isinstance(link, dict) or link.get("property_type_ref") != "link" or link_value.get("link_type_ref") != expected_type:
        findings.append({
            "code": "EMIT_ROUTE_INVALID",
            "message": f"emit route must resolve to {expected_type} Link",
        })
    elif link_value.get("parent_ref") != containing_function_ref:
        findings.append({
            "code": "EMIT_ROUTE_PARENT_MISMATCH",
            "message": "emit route parent_ref must be the containing Function",
        })
    return findings
