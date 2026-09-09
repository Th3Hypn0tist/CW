from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cw import validate_cw
from .event_logic import EventCandidate

class EventMappingError(ValueError): pass

@dataclass(frozen=True)
class EventMappingProposal:
    proposal_id:str
    owner_entity_ref:str
    target_function_ref:str
    target_function_qualified_name:str
    event_type_ref:str
    trigger_rule_ref:str
    status:str="TARGET_VALIDATED"
    canonical_ready:bool=False
    canonical_semantic_authority:bool=False


def _value(candidate,field): return getattr(candidate,field) if isinstance(candidate,EventCandidate) else candidate.get(field) if isinstance(candidate,dict) else None


def propose_event_mapping(cw:dict[str,Any],candidate:EventCandidate|dict[str,Any])->EventMappingProposal:
    validate_cw(cw)
    owner=_value(candidate,"owner_entity_ref"); qualified=_value(candidate,"function_qualified_name"); event_type=_value(candidate,"event_type_ref"); rule=_value(candidate,"trigger_rule_ref")
    if any(not isinstance(v,str) or not v for v in (owner,qualified,event_type,rule)): raise EventMappingError("Event mapping candidate fields missing")
    entity=next((e for e in cw.get("entities",[]) if isinstance(e,dict) and e.get("id")==owner),None)
    if entity is None or not owner.startswith("#FILE:"): raise EventMappingError(f"Event candidate owner #FILE does not exist in CW: {owner}")
    matches=[]
    for prop in entity.get("properties",[]):
        if not isinstance(prop,dict) or prop.get("property_type_ref")!="function": continue
        value=prop.get("value") if isinstance(prop.get("value"),dict) else {}; details=value.get("properties") if isinstance(value.get("properties"),dict) else {}
        if details.get("qualified_name")==qualified: matches.append(prop)
    if len(matches)!=1: raise EventMappingError(f"Event candidate target Function Property is {'missing' if not matches else 'ambiguous'}: {owner}::{qualified}")
    function_ref=matches[0].get("id")
    if not isinstance(function_ref,str) or not function_ref: raise EventMappingError("Event target Function Property id missing")
    return EventMappingProposal(f"EVENT_MAPPING::{rule}::{owner}::{qualified}",owner,function_ref,qualified,event_type,rule)
