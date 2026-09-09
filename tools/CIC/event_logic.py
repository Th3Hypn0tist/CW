from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class EventLogicError(ValueError):
    pass


@dataclass(frozen=True)
class EventTriggerRule:
    rule_id: str
    language_id: str
    evidence_kind: str
    evidence_value: str
    event_type_ref: str


@dataclass(frozen=True)
class EventCandidate:
    candidate_id: str
    owner_entity_ref: str
    function_qualified_name: str
    function_name: str
    function_owner: str | None
    event_type_ref: str
    trigger_rule_ref: str
    trigger_evidence_kind: str
    trigger_evidence_value: str
    span: dict[str, Any]
    canonical_ready: bool = False
    authority: str = "implementation_evidence"


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EventLogicError(f"{label} must be a non-empty string")
    return value


def _rule(record: EventTriggerRule | dict[str, Any]) -> EventTriggerRule:
    if isinstance(record, EventTriggerRule):
        return record
    if not isinstance(record, dict):
        raise EventLogicError("event trigger rule must be an object")
    return EventTriggerRule(
        rule_id=_text(record.get("rule_id"), "rule_id"),
        language_id=_text(record.get("language_id"), "language_id"),
        evidence_kind=_text(record.get("evidence_kind"), "evidence_kind"),
        evidence_value=_text(record.get("evidence_value"), "evidence_value"),
        event_type_ref=_text(record.get("event_type_ref"), "event_type_ref"),
    )


def _function_records(symbols: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for symbol in symbols:
        if not isinstance(symbol, dict):
            continue
        kind = symbol.get("kind")
        if kind in {"function", "method"}:
            yield symbol
            yield from _function_records(symbol.get("nested_functions", []))
        elif kind == "class":
            yield from _function_records(symbol.get("methods", []))


def _evidence_values(function: dict[str, Any], evidence_kind: str) -> tuple[str, ...]:
    if evidence_kind == "decorator_exact":
        decorators = function.get("decorators", [])
        if not isinstance(decorators, list):
            return ()
        return tuple(item for item in decorators if isinstance(item, str) and item)
    return ()


def detect_event_candidates(
    ir: dict[str, Any],
    rules: Iterable[EventTriggerRule | dict[str, Any]],
) -> tuple[EventCandidate, ...]:
    """Detect externally-triggerable function surfaces from explicit evidence rules only."""
    if not isinstance(ir, dict):
        raise EventLogicError("Code IR must be an object")

    normalized_rules = tuple(_rule(item) for item in rules)
    ids = [item.rule_id for item in normalized_rules]
    if len(ids) != len(set(ids)):
        raise EventLogicError("duplicate event trigger rule_id")

    candidates: list[EventCandidate] = []
    seen: set[tuple[str, str, str]] = set()

    files = ir.get("files", [])
    if not isinstance(files, list):
        raise EventLogicError("Code IR files must be an array")

    for file_record in files:
        if not isinstance(file_record, dict):
            continue
        path = file_record.get("path")
        canonical_owner_ref = file_record.get("canonical_file_ref")
        language_ir = file_record.get("language_ir")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(canonical_owner_ref, str)
            or not canonical_owner_ref.startswith("#FILE:")
            or not isinstance(language_ir, dict)
        ):
            continue
        language_id = language_ir.get("language_id")
        owner_entity_ref = canonical_owner_ref

        for function in _function_records(language_ir.get("symbols", [])):
            name = function.get("name")
            qualified_name = function.get("qualified_name")
            if not isinstance(name, str) or not name or not isinstance(qualified_name, str) or not qualified_name:
                continue
            function_owner = function.get("owner") if isinstance(function.get("owner"), str) and function.get("owner") else None
            span = function.get("span") if isinstance(function.get("span"), dict) else {}

            for rule in normalized_rules:
                if rule.language_id != language_id:
                    continue
                values = _evidence_values(function, rule.evidence_kind)
                if rule.evidence_value not in values:
                    continue
                semantic_key = (owner_entity_ref, qualified_name, rule.rule_id)
                if semantic_key in seen:
                    continue
                seen.add(semantic_key)
                candidates.append(EventCandidate(
                    candidate_id=f"EVENT_CANDIDATE::{owner_entity_ref}::{qualified_name}::{rule.rule_id}",
                    owner_entity_ref=owner_entity_ref,
                    function_qualified_name=qualified_name,
                    function_name=name,
                    function_owner=function_owner,
                    event_type_ref=rule.event_type_ref,
                    trigger_rule_ref=rule.rule_id,
                    trigger_evidence_kind=rule.evidence_kind,
                    trigger_evidence_value=rule.evidence_value,
                    span=dict(span),
                ))

    return tuple(sorted(candidates, key=lambda item: item.candidate_id))
