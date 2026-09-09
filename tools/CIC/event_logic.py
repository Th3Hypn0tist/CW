from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class EventLogicError(ValueError): pass


@dataclass(frozen=True)
class EventTriggerRule:
    rule_id:str
    language_id:str
    evidence_kind:str
    evidence_value:str
    event_type_ref:str


@dataclass(frozen=True)
class EventCandidate:
    candidate_id:str
    owner_entity_ref:str
    function_qualified_name:str
    function_name:str
    function_owner:str|None
    event_type_ref:str
    trigger_rule_ref:str
    trigger_evidence_kind:str
    trigger_evidence_value:str
    span:dict[str,Any]
    canonical_ready:bool=False
    authority:str="implementation_evidence"


def _rule(record):
    if isinstance(record,EventTriggerRule): return record
    if not isinstance(record,dict): raise EventLogicError("event trigger rule must be an object")
    values=[record.get(k) for k in ("rule_id","language_id","evidence_kind","evidence_value","event_type_ref")]
    if any(not isinstance(v,str) or not v for v in values): raise EventLogicError("event trigger rule fields must be non-empty strings")
    return EventTriggerRule(*values)


def _function_records(symbols):
    for symbol in symbols:
        if not isinstance(symbol,dict): continue
        kind=symbol.get("kind")
        if kind in {"function","method"}:
            yield symbol
            yield from _function_records(symbol.get("nested_functions",[]))
        elif kind=="class": yield from _function_records(symbol.get("methods",[]))


def detect_event_candidates(ir:dict[str,Any],rules:Iterable[EventTriggerRule|dict[str,Any]])->tuple[EventCandidate,...]:
    if not isinstance(ir,dict): raise EventLogicError("Code IR must be an object")
    normalized=tuple(_rule(item) for item in rules)
    if len({r.rule_id for r in normalized})!=len(normalized): raise EventLogicError("duplicate event trigger rule_id")
    result=[]; seen=set()
    for file_record in ir.get("files",[]):
        if not isinstance(file_record,dict): continue
        lir=file_record.get("language_ir"); owner=file_record.get("canonical_file_ref")
        if not isinstance(lir,dict) or not isinstance(owner,str) or not owner.startswith("#FILE:"): continue
        for function in _function_records(lir.get("symbols",[])):
            name=function.get("name"); qualified=function.get("qualified_name")
            if not isinstance(name,str) or not isinstance(qualified,str): continue
            for rule in normalized:
                if rule.language_id!=lir.get("language_id") or rule.evidence_kind!="decorator_exact": continue
                decorators=function.get("decorators",[])
                if not isinstance(decorators,list) or rule.evidence_value not in decorators: continue
                key=(owner,qualified,rule.rule_id)
                if key in seen: continue
                seen.add(key); result.append(EventCandidate(f"EVENT_CANDIDATE::{owner}::{qualified}::{rule.rule_id}",owner,qualified,name,function.get("owner") if isinstance(function.get("owner"),str) else None,rule.event_type_ref,rule.rule_id,rule.evidence_kind,rule.evidence_value,function.get("span") if isinstance(function.get("span"),dict) else {}))
    return tuple(sorted(result,key=lambda item:item.candidate_id))
