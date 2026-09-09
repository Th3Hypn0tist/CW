from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cw import validate_cw

class EventCausalityError(ValueError): pass

@dataclass(frozen=True)
class CodeEventCausalityReport:
    event_ref:str
    status:str
    handler_targets:tuple[str,...]
    effect_refs:tuple[str,...]
    handler_missing:bool
    effect_missing:bool
    require_effect:bool
    canonical_semantic_authority:bool=False


def _index(cw):
    result={}
    for entity in cw.get("entities",[]):
        if not isinstance(entity,dict): continue
        if isinstance(entity.get("id"),str): result[entity["id"]]=("entity",entity)
        for prop in entity.get("properties",[]):
            if isinstance(prop,dict) and isinstance(prop.get("id"),str): result[prop["id"]]=("property",prop)
    return result


def evaluate_code_event_causality(cw:dict[str,Any],event_ref:str,*,require_effect:bool=False)->CodeEventCausalityReport:
    validate_cw(cw); index=_index(cw); hit=index.get(event_ref)
    if hit is None or hit[0]!="property" or hit[1].get("property_type_ref")!="event": raise EventCausalityError(f"event_ref must resolve to an Event Property: {event_ref}")
    handlers=[]; effects=[]
    for entity in cw.get("entities",[]):
        for prop in entity.get("properties",[]):
            if not isinstance(prop,dict) or prop.get("property_type_ref")!="link": continue
            value=prop.get("value") if isinstance(prop.get("value"),dict) else {}; kind=value.get("link_type_ref")
            if value.get("parent_ref")!=event_ref: continue
            child=value.get("child_ref"); target=index.get(child)
            if kind=="event_handler":
                if prop.get("ruleset_ref")!="RULESET_LINK_EVENT_HANDLER" or target is None or target[0]!="property" or target[1].get("property_type_ref")!="function": raise EventCausalityError(f"event_handler target must be Function Property: {child}")
                handlers.append(str(child))
            elif kind=="event_effect":
                if prop.get("ruleset_ref")!="RULESET_LINK_EVENT_EFFECT" or target is None or target[0]!="property" or target[1].get("property_type_ref")!="effect": raise EventCausalityError(f"event_effect target must be Effect Property: {child}")
                effects.append(str(child))
    h=tuple(sorted(set(handlers))); e=tuple(sorted(set(effects))); missing_h=not h; missing_e=not e
    return CodeEventCausalityReport(event_ref,"UNSOLVED" if missing_h or (require_effect and missing_e) else "SOLVED",h,e,missing_h,missing_e,require_effect)
