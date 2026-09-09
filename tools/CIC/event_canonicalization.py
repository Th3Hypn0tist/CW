from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .cw import validate_cw
from .event_causality import evaluate_code_event_causality
from .event_mapping import EventMappingProposal

class EventCanonicalizationError(ValueError): pass

@dataclass(frozen=True)
class CanonicalEventProposal:
    owner_entity_ref:str
    event_property:dict[str,Any]
    handler_link_property:dict[str,Any]
    target_function_ref:str
    status:str="PROPOSED"
    canonical_ready:bool=False
    canonical_semantic_authority:bool=False

@dataclass(frozen=True)
class ApprovedCanonicalEventChange:
    proposal:CanonicalEventProposal
    status:str="VALIDATED_FOR_APPLY"
    apply_ready:bool=True
    canonical_semantic_authority:bool=False


def _safe(value:str)->str:
    return value.replace("::","__").replace("#","").replace(":","_").replace("/","_").replace("\\","_").replace("<","_").replace(">","_").replace(" ","_")


def propose_canonical_event(mapping:EventMappingProposal)->CanonicalEventProposal:
    if not isinstance(mapping,EventMappingProposal) or mapping.status!="TARGET_VALIDATED": raise EventCanonicalizationError("canonical Event proposal requires validated EventMappingProposal")
    event_id=f"EVENT::{_safe(mapping.owner_entity_ref)}::{mapping.target_function_qualified_name}::{mapping.trigger_rule_ref}"; handler_id=f"LINK::EVENT_HANDLER::{_safe(event_id)}"
    event={"id":event_id,"property_type_ref":"event","ruleset_ref":"RULESET_EVENT","status":"unlocked","value":{"event_type_ref":mapping.event_type_ref,"properties":{"implementation_evidence_ref":mapping.proposal_id,"trigger_rule_ref":mapping.trigger_rule_ref,"target_function_qualified_name":mapping.target_function_qualified_name}}}
    handler={"id":handler_id,"property_type_ref":"link","ruleset_ref":"RULESET_LINK_EVENT_HANDLER","status":"unlocked","value":{"link_type_ref":"event_handler","parent_ref":event_id,"child_ref":mapping.target_function_ref,"properties":{"implementation_evidence_ref":mapping.proposal_id,"trigger_rule_ref":mapping.trigger_rule_ref}}}
    return CanonicalEventProposal(mapping.owner_entity_ref,event,handler,mapping.target_function_ref)


def approve_canonical_event(cw:dict[str,Any],proposal:CanonicalEventProposal)->ApprovedCanonicalEventChange:
    validate_cw(cw)
    ids={e.get("id") for e in cw.get("entities",[]) if isinstance(e,dict)} | {p.get("id") for e in cw.get("entities",[]) if isinstance(e,dict) for p in e.get("properties",[]) if isinstance(p,dict)}
    if proposal.event_property.get("id") in ids or proposal.handler_link_property.get("id") in ids: raise EventCanonicalizationError("proposed Event identity already exists")
    target=next((p for e in cw.get("entities",[]) if isinstance(e,dict) for p in e.get("properties",[]) if isinstance(p,dict) and p.get("id")==proposal.target_function_ref and p.get("property_type_ref")=="function"),None)
    if target is None: raise EventCanonicalizationError(f"proposed Event target must resolve to Function Property: {proposal.target_function_ref}")
    return ApprovedCanonicalEventChange(proposal)


def apply_canonical_event(cw:dict[str,Any],approved:ApprovedCanonicalEventChange)->dict[str,Any]:
    validate_cw(cw); result=copy.deepcopy(cw); proposal=approved.proposal
    owner=next((e for e in result.get("entities",[]) if isinstance(e,dict) and e.get("id")==proposal.owner_entity_ref),None)
    if owner is None: raise EventCanonicalizationError(f"Event owner #FILE disappeared before apply: {proposal.owner_entity_ref}")
    owner["properties"].extend([copy.deepcopy(proposal.event_property),copy.deepcopy(proposal.handler_link_property)]); validate_cw(result)
    report=evaluate_code_event_causality(result,proposal.event_property["id"])
    if report.status!="SOLVED": raise EventCanonicalizationError("applied Event failed explicit handler target validation")
    return result
