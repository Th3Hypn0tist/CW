from __future__ import annotations

import ast
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


def _ast_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _ast_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _registration_handler_symbol(function: dict[str, Any], constructor: str) -> str | None:
    """Return handler=<symbol> from an explicit returned constructor call.

    This inspects only the archived source of the candidate factory Function. It
    does not infer runtime registration from naming, directories, or call graphs.
    """
    source = function.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    try:
        tree = ast.parse(source, type_comments=True)
    except SyntaxError:
        return None
    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    node = tree.body[0]
    for statement in node.body:
        if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
            continue
        call = statement.value
        if _ast_name(call.func) != constructor:
            continue
        for keyword in call.keywords:
            if keyword.arg != "handler":
                continue
            return _ast_name(keyword.value)
    return None


def _candidate_from_function(
    *,
    owner_entity_ref: str,
    function: dict[str, Any],
    rule: EventTriggerRule,
    evidence_kind: str,
    evidence_value: str,
) -> EventCandidate | None:
    name = function.get("name")
    qualified_name = function.get("qualified_name")
    if not isinstance(name, str) or not name or not isinstance(qualified_name, str) or not qualified_name:
        return None
    function_owner = function.get("owner") if isinstance(function.get("owner"), str) and function.get("owner") else None
    span = function.get("span") if isinstance(function.get("span"), dict) else {}
    return EventCandidate(
        candidate_id=f"EVENT_CANDIDATE::{owner_entity_ref}::{qualified_name}::{rule.rule_id}",
        owner_entity_ref=owner_entity_ref,
        function_qualified_name=qualified_name,
        function_name=name,
        function_owner=function_owner,
        event_type_ref=rule.event_type_ref,
        trigger_rule_ref=rule.rule_id,
        trigger_evidence_kind=evidence_kind,
        trigger_evidence_value=evidence_value,
        span=dict(span),
    )


def detect_event_candidates(
    ir: dict[str, Any],
    rules: Iterable[EventTriggerRule | dict[str, Any]],
) -> tuple[EventCandidate, ...]:
    """Detect externally-triggerable function surfaces from explicit evidence rules only.

    Supported evidence kinds:
      decorator_exact      exact Function decorator text
      registration_handler
        a Function explicitly returns the configured constructor and binds its
        handler= keyword to another Function in the same canonical #FILE Entity
    """
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
        functions = list(_function_records(language_ir.get("symbols", [])))
        top_level_by_name = {
            function.get("name"): function
            for function in functions
            if isinstance(function.get("name"), str) and not function.get("owner")
        }

        for rule in normalized_rules:
            if rule.language_id != language_id or rule.evidence_kind != "registration_handler":
                continue
            for factory in functions:
                if factory.get("owner"):
                    continue
                handler_symbol = _registration_handler_symbol(factory, rule.evidence_value)
                if not isinstance(handler_symbol, str) or not handler_symbol:
                    continue
                handler = top_level_by_name.get(handler_symbol)
                if not isinstance(handler, dict):
                    continue
                candidate = _candidate_from_function(
                    owner_entity_ref=owner_entity_ref,
                    function=handler,
                    rule=rule,
                    evidence_kind=rule.evidence_kind,
                    evidence_value=rule.evidence_value,
                )
                if candidate is None:
                    continue
                semantic_key = (owner_entity_ref, candidate.function_qualified_name, rule.rule_id)
                if semantic_key in seen:
                    continue
                seen.add(semantic_key)
                candidates.append(candidate)

        for function in functions:
            name = function.get("name")
            qualified_name = function.get("qualified_name")
            if not isinstance(name, str) or not name or not isinstance(qualified_name, str) or not qualified_name:
                continue
            for rule in normalized_rules:
                if rule.language_id != language_id or rule.evidence_kind == "registration_handler":
                    continue
                values = _evidence_values(function, rule.evidence_kind)
                if rule.evidence_value not in values:
                    continue
                semantic_key = (owner_entity_ref, qualified_name, rule.rule_id)
                if semantic_key in seen:
                    continue
                seen.add(semantic_key)
                candidate = _candidate_from_function(
                    owner_entity_ref=owner_entity_ref,
                    function=function,
                    rule=rule,
                    evidence_kind=rule.evidence_kind,
                    evidence_value=rule.evidence_value,
                )
                if candidate is not None:
                    candidates.append(candidate)

    return tuple(sorted(candidates, key=lambda item: item.candidate_id))
