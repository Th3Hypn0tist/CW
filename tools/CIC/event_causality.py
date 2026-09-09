from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from CIC.cw import validate_cw


class EventCausalityError(ValueError):
    pass


@dataclass(frozen=True)
class CodeEventCausalityReport:
    event_ref: str
    status: str
    handler_targets: tuple[str, ...]
    effect_refs: tuple[str, ...]
    handler_missing: bool
    effect_missing: bool
    require_effect: bool
    canonical_semantic_authority: bool = False


def _identity_index(cw: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    index: dict[str, tuple[str, dict[str, Any]]] = {}
    for entity in cw.get("entities", []):
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        if isinstance(entity_id, str):
            index[entity_id] = ("entity", entity)
        for prop in entity.get("properties", []):
            if isinstance(prop, dict) and isinstance(prop.get("id"), str):
                index[prop["id"]] = ("property", prop)
    return index


def _property_type(index: dict[str, tuple[str, dict[str, Any]]], ref: str) -> str | None:
    hit = index.get(ref)
    if hit is None or hit[0] != "property":
        return None
    value = hit[1].get("property_type_ref")
    return value if isinstance(value, str) else None


def evaluate_code_event_causality(
    cw: dict[str, Any],
    event_ref: str,
    *,
    require_effect: bool = False,
) -> CodeEventCausalityReport:
    """Evaluate explicit target/causality for one code-import Event Property.

    Code-import profile rule: an imported Event must have at least one explicit
    event_handler Link to a Function Property. Handler binding is implementation
    targeting only and never counts as Event Effect causality.

    Effect completeness is optional unless `require_effect=True`; when modeled,
    event_effect must be oriented Event Property -> Effect Property.
    """
    validate_cw(cw)
    if not isinstance(event_ref, str) or not event_ref:
        raise EventCausalityError("event_ref must be non-empty")

    index = _identity_index(cw)
    if _property_type(index, event_ref) != "event":
        raise EventCausalityError(f"event_ref must resolve to an Event Property: {event_ref}")

    handlers: list[str] = []
    effects: list[str] = []

    for entity in cw.get("entities", []):
        for prop in entity.get("properties", []):
            if not isinstance(prop, dict) or prop.get("property_type_ref") != "link":
                continue
            value = prop.get("value")
            if not isinstance(value, dict):
                continue
            link_type = value.get("link_type_ref")
            parent_ref = value.get("parent_ref")
            child_ref = value.get("child_ref")

            if link_type == "event_handler":
                if child_ref == event_ref:
                    raise EventCausalityError(
                        f"event_handler direction is reversed for {event_ref}; Event must be parent_ref"
                    )
                if parent_ref != event_ref:
                    continue
                if prop.get("ruleset_ref") != "RULESET_LINK_EVENT_HANDLER":
                    raise EventCausalityError(f"event_handler uses wrong ruleset: {prop.get('id')}")
                if _property_type(index, str(child_ref)) != "function":
                    raise EventCausalityError(
                        f"event_handler target must be Function Property: {child_ref}"
                    )
                handlers.append(str(child_ref))

            elif link_type == "event_effect":
                if child_ref == event_ref:
                    raise EventCausalityError(
                        f"event_effect direction is reversed for {event_ref}; Event must be parent_ref"
                    )
                if parent_ref != event_ref:
                    continue
                if prop.get("ruleset_ref") != "RULESET_LINK_EVENT_EFFECT":
                    raise EventCausalityError(f"event_effect uses wrong ruleset: {prop.get('id')}")
                if _property_type(index, str(child_ref)) != "effect":
                    raise EventCausalityError(
                        f"event_effect target must be Effect Property: {child_ref}"
                    )
                effects.append(str(child_ref))

    handler_targets = tuple(sorted(set(handlers)))
    effect_refs = tuple(sorted(set(effects)))
    handler_missing = not handler_targets
    effect_missing = not effect_refs

    if handler_missing or (require_effect and effect_missing):
        status = "UNSOLVED"
    else:
        status = "SOLVED"

    return CodeEventCausalityReport(
        event_ref=event_ref,
        status=status,
        handler_targets=handler_targets,
        effect_refs=effect_refs,
        handler_missing=handler_missing,
        effect_missing=effect_missing,
        require_effect=require_effect,
    )
