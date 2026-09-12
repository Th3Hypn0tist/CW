from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from CIC.cw import validate_cw
from CIC.event_logic import EventCandidate


class EventMappingError(ValueError):
    pass


@dataclass(frozen=True)
class EventMappingProposal:
    proposal_id: str
    owner_entity_ref: str
    target_function_ref: str
    target_function_qualified_name: str
    event_type_ref: str
    trigger_rule_ref: str
    event_identity: str | None = None
    status: str = "TARGET_VALIDATED"
    canonical_ready: bool = False
    canonical_semantic_authority: bool = False


def _candidate_value(candidate: EventCandidate | dict[str, Any], field: str) -> Any:
    if isinstance(candidate, EventCandidate):
        return getattr(candidate, field)
    if isinstance(candidate, dict):
        return candidate.get(field)
    raise EventMappingError("Event mapping candidate must be EventCandidate or object")


def propose_event_mapping(
    cw: dict[str, Any],
    candidate: EventCandidate | dict[str, Any],
) -> EventMappingProposal:
    """Validate an Event candidate's exact canonical CW target without mutating CW."""
    validate_cw(cw)

    owner_ref = _candidate_value(candidate, "owner_entity_ref")
    qualified_name = _candidate_value(candidate, "function_qualified_name")
    event_type_ref = _candidate_value(candidate, "event_type_ref")
    trigger_rule_ref = _candidate_value(candidate, "trigger_rule_ref")
    event_identity = _candidate_value(candidate, "event_identity")
    for value, label in (
        (owner_ref, "owner_entity_ref"),
        (qualified_name, "function_qualified_name"),
        (event_type_ref, "event_type_ref"),
        (trigger_rule_ref, "trigger_rule_ref"),
    ):
        if not isinstance(value, str) or not value:
            raise EventMappingError(f"Event mapping candidate {label} missing")
    if event_identity is not None and (not isinstance(event_identity, str) or not event_identity):
        raise EventMappingError("Event mapping candidate event_identity must be a non-empty string when present")

    owner = next((entity for entity in cw.get("entities", []) if entity.get("id") == owner_ref), None)
    if owner is None:
        raise EventMappingError(f"Event candidate owner #FILE does not exist in CW: {owner_ref}")
    if not str(owner_ref).startswith("#FILE:"):
        raise EventMappingError(f"Event candidate owner must be canonical #FILE identity: {owner_ref}")

    matches: list[dict[str, Any]] = []
    for prop in owner.get("properties", []):
        if not isinstance(prop, dict) or prop.get("property_type_ref") != "function":
            continue
        value = prop.get("value")
        details = value.get("properties") if isinstance(value, dict) else None
        if isinstance(details, dict) and details.get("qualified_name") == qualified_name:
            matches.append(prop)

    if not matches:
        raise EventMappingError(
            f"Event candidate target Function Property does not exist: {owner_ref}::{qualified_name}"
        )
    if len(matches) > 1:
        raise EventMappingError(
            f"Event candidate target Function Property is ambiguous: {owner_ref}::{qualified_name}"
        )

    function_ref = matches[0].get("id")
    if not isinstance(function_ref, str) or not function_ref:
        raise EventMappingError("Event candidate target Function Property id missing")

    identity_suffix = f"::{event_identity}" if event_identity is not None else ""
    return EventMappingProposal(
        proposal_id=f"EVENT_MAPPING::{trigger_rule_ref}::{owner_ref}::{qualified_name}{identity_suffix}",
        owner_entity_ref=owner_ref,
        target_function_ref=function_ref,
        target_function_qualified_name=qualified_name,
        event_type_ref=event_type_ref,
        trigger_rule_ref=trigger_rule_ref,
        event_identity=event_identity,
    )
