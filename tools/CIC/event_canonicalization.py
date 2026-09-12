from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from CIC.cw import validate_cw
from CIC.event_causality import evaluate_code_event_causality
from CIC.event_mapping import EventMappingProposal


class EventCanonicalizationError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalEventProposal:
    owner_entity_ref: str
    event_property: dict[str, Any]
    handler_link_property: dict[str, Any]
    target_function_ref: str
    status: str = "PROPOSED"
    canonical_ready: bool = False
    canonical_semantic_authority: bool = False


@dataclass(frozen=True)
class ApprovedCanonicalEventChange:
    proposal: CanonicalEventProposal
    status: str = "VALIDATED_FOR_APPLY"
    apply_ready: bool = True
    canonical_semantic_authority: bool = False


def _safe_fragment(value: str) -> str:
    return (
        value.replace("::", "__")
        .replace("#", "")
        .replace(":", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace(" ", "_")
    )


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


def propose_canonical_event(mapping: EventMappingProposal) -> CanonicalEventProposal:
    if not isinstance(mapping, EventMappingProposal):
        raise EventCanonicalizationError("canonical Event proposal requires EventMappingProposal")
    if mapping.status != "TARGET_VALIDATED":
        raise EventCanonicalizationError("Event mapping target must be validated before canonical proposal")
    if mapping.canonical_ready or mapping.canonical_semantic_authority:
        raise EventCanonicalizationError("Event mapping proposal must remain noncanonical evidence")

    owner_ref = mapping.owner_entity_ref
    function_ref = mapping.target_function_ref
    event_type_ref = mapping.event_type_ref
    trigger_rule_ref = mapping.trigger_rule_ref
    qualified_name = mapping.target_function_qualified_name
    event_identity = mapping.event_identity

    for value, label in (
        (owner_ref, "owner_entity_ref"),
        (function_ref, "target_function_ref"),
        (event_type_ref, "event_type_ref"),
        (trigger_rule_ref, "trigger_rule_ref"),
        (qualified_name, "target_function_qualified_name"),
    ):
        if not isinstance(value, str) or not value:
            raise EventCanonicalizationError(f"Event canonicalization {label} missing")
    if event_identity is not None and (not isinstance(event_identity, str) or not event_identity):
        raise EventCanonicalizationError("Event event_identity must be a non-empty string when present")

    if not owner_ref.startswith("#FILE:"):
        raise EventCanonicalizationError(f"Event owner must be canonical #FILE identity: {owner_ref}")

    semantic_name = event_identity if event_identity is not None else qualified_name
    event_id = f"EVENT::{_safe_fragment(owner_ref)}::{event_type_ref}::{_safe_fragment(semantic_name)}::{trigger_rule_ref}"
    handler_id = f"LINK::EVENT_HANDLER::{_safe_fragment(event_id)}"

    event_properties = {
        "implementation_evidence_ref": mapping.proposal_id,
        "trigger_rule_ref": trigger_rule_ref,
        "target_function_qualified_name": qualified_name,
    }
    if event_identity is not None:
        event_properties["event_identity"] = event_identity

    event_property = {
        "id": event_id,
        "property_type_ref": "event",
        "ruleset_ref": "RULESET_EVENT",
        "status": "unlocked",
        "value": {
            "event_type_ref": event_type_ref,
            "properties": event_properties,
        },
    }

    handler_link_property = {
        "id": handler_id,
        "property_type_ref": "link",
        "ruleset_ref": "RULESET_LINK_EVENT_HANDLER",
        "status": "unlocked",
        "value": {
            "link_type_ref": "event_handler",
            "parent_ref": event_id,
            "child_ref": function_ref,
            "properties": {
                "implementation_evidence_ref": mapping.proposal_id,
                "trigger_rule_ref": trigger_rule_ref,
            },
        },
    }

    return CanonicalEventProposal(
        owner_entity_ref=owner_ref,
        event_property=event_property,
        handler_link_property=handler_link_property,
        target_function_ref=function_ref,
    )


def approve_canonical_event(cw: dict[str, Any], proposal: CanonicalEventProposal) -> ApprovedCanonicalEventChange:
    validate_cw(cw)
    if not isinstance(proposal, CanonicalEventProposal):
        raise EventCanonicalizationError("Event approval requires CanonicalEventProposal")
    if proposal.status != "PROPOSED" or proposal.canonical_ready:
        raise EventCanonicalizationError("Event proposal must be an unready PROPOSED change")

    index = _identity_index(cw)
    owner_hit = index.get(proposal.owner_entity_ref)
    if owner_hit is None or owner_hit[0] != "entity" or not proposal.owner_entity_ref.startswith("#FILE:"):
        raise EventCanonicalizationError(f"Event owner #FILE does not exist: {proposal.owner_entity_ref}")

    event = proposal.event_property
    handler = proposal.handler_link_property
    event_id = event.get("id") if isinstance(event, dict) else None
    handler_id = handler.get("id") if isinstance(handler, dict) else None
    if not isinstance(event_id, str) or not event_id:
        raise EventCanonicalizationError("proposed Event Property id missing")
    if not isinstance(handler_id, str) or not handler_id:
        raise EventCanonicalizationError("proposed event_handler Link id missing")
    for identity in (event_id, handler_id):
        if identity in index:
            raise EventCanonicalizationError(f"proposed Event identity already exists: {identity}")

    if event.get("property_type_ref") != "event" or event.get("ruleset_ref") != "RULESET_EVENT":
        raise EventCanonicalizationError("proposed Event must use event / RULESET_EVENT")
    event_value = event.get("value")
    if not isinstance(event_value, dict) or not isinstance(event_value.get("event_type_ref"), str) or not event_value.get("event_type_ref"):
        raise EventCanonicalizationError("proposed Event event_type_ref missing")

    if handler.get("property_type_ref") != "link" or handler.get("ruleset_ref") != "RULESET_LINK_EVENT_HANDLER":
        raise EventCanonicalizationError("proposed handler must use link / RULESET_LINK_EVENT_HANDLER")
    handler_value = handler.get("value")
    if not isinstance(handler_value, dict) or handler_value.get("link_type_ref") != "event_handler":
        raise EventCanonicalizationError("proposed handler link_type_ref must be event_handler")
    if handler_value.get("parent_ref") != event_id:
        raise EventCanonicalizationError("proposed event_handler parent_ref must be the Event Property")
    if handler_value.get("child_ref") != proposal.target_function_ref:
        raise EventCanonicalizationError("proposed event_handler child_ref must be target Function Property")

    target_hit = index.get(proposal.target_function_ref)
    if target_hit is None or target_hit[0] != "property" or target_hit[1].get("property_type_ref") != "function":
        raise EventCanonicalizationError(f"proposed Event target must resolve to Function Property: {proposal.target_function_ref}")

    return ApprovedCanonicalEventChange(proposal=proposal)


def apply_canonical_event(cw: dict[str, Any], approved: ApprovedCanonicalEventChange) -> dict[str, Any]:
    validate_cw(cw)
    if not isinstance(approved, ApprovedCanonicalEventChange):
        raise EventCanonicalizationError("Event apply requires ApprovedCanonicalEventChange")
    if approved.status != "VALIDATED_FOR_APPLY" or not approved.apply_ready:
        raise EventCanonicalizationError("Event change is not validated for apply")

    proposal = approved.proposal
    result = copy.deepcopy(cw)
    owner = next((entity for entity in result.get("entities", []) if entity.get("id") == proposal.owner_entity_ref), None)
    if owner is None:
        raise EventCanonicalizationError(f"Event owner #FILE disappeared before apply: {proposal.owner_entity_ref}")

    owner["properties"].append(copy.deepcopy(proposal.event_property))
    owner["properties"].append(copy.deepcopy(proposal.handler_link_property))
    validate_cw(result)

    report = evaluate_code_event_causality(result, proposal.event_property["id"])
    if report.status != "SOLVED" or report.handler_missing:
        raise EventCanonicalizationError("applied Event failed explicit handler target validation")
    return result
