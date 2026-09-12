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
    identity_keyword: str | None = None


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
    event_identity: str | None = None
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
    identity_keyword = record.get("identity_keyword")
    if identity_keyword is not None and (not isinstance(identity_keyword, str) or not identity_keyword):
        raise EventLogicError("identity_keyword must be a non-empty string when present")
    return EventTriggerRule(
        rule_id=_text(record.get("rule_id"), "rule_id"),
        language_id=_text(record.get("language_id"), "language_id"),
        evidence_kind=_text(record.get("evidence_kind"), "evidence_kind"),
        evidence_value=_text(record.get("evidence_value"), "evidence_value"),
        event_type_ref=_text(record.get("event_type_ref"), "event_type_ref"),
        identity_keyword=identity_keyword,
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


def _module_literals(symbols: Iterable[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for symbol in symbols:
        if not isinstance(symbol, dict) or symbol.get("kind") != "variable" or "literal_value" not in symbol:
            continue
        names = symbol.get("names")
        if not isinstance(names, list) or len(names) != 1 or not isinstance(names[0], str) or not names[0]:
            continue
        result[names[0]] = symbol["literal_value"]
    return result


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


def _resolve_literal_node(node: ast.AST, module_literals: dict[str, Any]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
        return node.value
    if isinstance(node, ast.Name):
        value = module_literals.get(node.id)
        if isinstance(value, str) and value:
            return value
    return None


def _registration_binding(
    function: dict[str, Any],
    constructor: str,
    *,
    identity_keyword: str | None,
    module_literals: dict[str, Any],
) -> tuple[str, str | None] | None:
    """Return explicit handler and optional source-backed identity from a returned constructor call."""
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
        keywords = {kw.arg: kw.value for kw in call.keywords if isinstance(kw.arg, str)}
        handler_node = keywords.get("handler")
        handler_symbol = _ast_name(handler_node)
        if not isinstance(handler_symbol, str) or not handler_symbol:
            continue
        event_identity = None
        if identity_keyword is not None:
            identity_node = keywords.get(identity_keyword)
            if identity_node is None:
                continue
            event_identity = _resolve_literal_node(identity_node, module_literals)
            if event_identity is None:
                continue
        return handler_symbol, event_identity
    return None


def _candidate_from_function(
    *,
    owner_entity_ref: str,
    function: dict[str, Any],
    rule: EventTriggerRule,
    evidence_kind: str,
    evidence_value: str,
    event_identity: str | None = None,
) -> EventCandidate | None:
    name = function.get("name")
    qualified_name = function.get("qualified_name")
    if not isinstance(name, str) or not name or not isinstance(qualified_name, str) or not qualified_name:
        return None
    function_owner = function.get("owner") if isinstance(function.get("owner"), str) and function.get("owner") else None
    span = function.get("span") if isinstance(function.get("span"), dict) else {}
    identity_part = f"::{event_identity}" if event_identity is not None else ""
    return EventCandidate(
        candidate_id=f"EVENT_CANDIDATE::{owner_entity_ref}::{qualified_name}::{rule.rule_id}{identity_part}",
        owner_entity_ref=owner_entity_ref,
        function_qualified_name=qualified_name,
        function_name=name,
        function_owner=function_owner,
        event_type_ref=rule.event_type_ref,
        trigger_rule_ref=rule.rule_id,
        trigger_evidence_kind=evidence_kind,
        trigger_evidence_value=evidence_value,
        span=dict(span),
        event_identity=event_identity,
    )


def detect_event_candidates(
    ir: dict[str, Any],
    rules: Iterable[EventTriggerRule | dict[str, Any]],
) -> tuple[EventCandidate, ...]:
    """Detect externally-triggerable Function surfaces from explicit evidence rules only."""
    if not isinstance(ir, dict):
        raise EventLogicError("Code IR must be an object")

    normalized_rules = tuple(_rule(item) for item in rules)
    ids = [item.rule_id for item in normalized_rules]
    if len(ids) != len(set(ids)):
        raise EventLogicError("duplicate event trigger rule_id")

    candidates: list[EventCandidate] = []
    seen: set[tuple[str, str, str, str | None]] = set()

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
        symbols = language_ir.get("symbols", []) if isinstance(language_ir.get("symbols"), list) else []
        functions = list(_function_records(symbols))
        module_literals = _module_literals(symbols)
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
                binding = _registration_binding(
                    factory,
                    rule.evidence_value,
                    identity_keyword=rule.identity_keyword,
                    module_literals=module_literals,
                )
                if binding is None:
                    continue
                handler_symbol, event_identity = binding
                handler = top_level_by_name.get(handler_symbol)
                if not isinstance(handler, dict):
                    continue
                candidate = _candidate_from_function(
                    owner_entity_ref=owner_entity_ref,
                    function=handler,
                    rule=rule,
                    evidence_kind=rule.evidence_kind,
                    evidence_value=rule.evidence_value,
                    event_identity=event_identity,
                )
                if candidate is None:
                    continue
                semantic_key = (owner_entity_ref, candidate.function_qualified_name, rule.rule_id, event_identity)
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
                semantic_key = (owner_entity_ref, qualified_name, rule.rule_id, None)
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
