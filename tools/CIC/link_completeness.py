from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class LinkCompletenessError(ValueError): pass

@dataclass(frozen=True)
class ObligationVerdict:
    obligation_id:str
    required:bool
    state:str
    matched_link_ids:tuple[str,...]
    candidate_link_ids:tuple[str,...]
    min_count:int
    max_count:int|None
    actual_count:int
    reason:str|None=None

@dataclass(frozen=True)
class LinkCompletenessResult:
    state:str
    obligations:tuple[ObligationVerdict,...]
    @property
    def solved(self)->bool: return self.state=="SOLVED"

_VALID_RESOLUTION={"RESOLVED","UNRESOLVED","INVALID"}

def _text(record,key,required=True):
    value=record.get(key)
    if value is None and not required:return None
    if not isinstance(value,str) or not value:raise LinkCompletenessError(f"{key} must be a non-empty string")
    return value

def _obligation(record):
    if not isinstance(record,dict):raise LinkCompletenessError("link obligation must be an object")
    required=record.get("required",True); minimum=record.get("min_count",1 if required else 0); maximum=record.get("max_count")
    if not isinstance(required,bool):raise LinkCompletenessError("required must be boolean")
    if not isinstance(minimum,int) or minimum<0:raise LinkCompletenessError("min_count must be non-negative")
    if maximum is not None and (not isinstance(maximum,int) or maximum<minimum):raise LinkCompletenessError("max_count must be null or >= min_count")
    return {"obligation_id":_text(record,"obligation_id"),"required":required,"link_type_ref":_text(record,"link_type_ref"),"parent_ref":_text(record,"parent_ref"),"child_ref":_text(record,"child_ref",False),"min_count":minimum,"max_count":maximum}
def _link(record):
    if not isinstance(record,dict):raise LinkCompletenessError("link evidence must be an object")
    status=record.get("resolution_status","RESOLVED"); refs=record.get("obligation_refs",[])
    if status not in _VALID_RESOLUTION:raise LinkCompletenessError(f"invalid resolution_status: {status!r}")
    if not isinstance(refs,list) or any(not isinstance(item,str) or not item for item in refs):raise LinkCompletenessError("obligation_refs must be string array")
    return {"link_id":_text(record,"link_id"),"link_type_ref":_text(record,"link_type_ref"),"parent_ref":_text(record,"parent_ref",False),"child_ref":_text(record,"child_ref",False),"resolution_status":status,"obligation_refs":tuple(refs)}
def _matches(obligation,link):
    return link["link_type_ref"]==obligation["link_type_ref"] and link["parent_ref"]==obligation["parent_ref"] and (obligation["child_ref"] is None or link["child_ref"]==obligation["child_ref"]) and link["child_ref"] is not None

def evaluate_required_links(obligations:Iterable[dict[str,Any]],links:Iterable[dict[str,Any]])->LinkCompletenessResult:
    obligations=[_obligation(item) for item in obligations]; links=[_link(item) for item in links]; ids=[item["obligation_id"] for item in obligations]
    if len(ids)!=len(set(ids)):raise LinkCompletenessError("duplicate obligation_id")
    known=set(ids)
    for link in links:
        unknown=set(link["obligation_refs"])-known
        if unknown:raise LinkCompletenessError(f"link {link['link_id']} references unknown obligations: {sorted(unknown)}")
    verdicts=[]
    for obligation in obligations:
        oid=obligation["obligation_id"]; attributed=[link for link in links if oid in link["obligation_refs"]]; exact=[link for link in links if link["resolution_status"]=="RESOLVED" and _matches(obligation,link)]
        unique={(link["link_type_ref"],link["parent_ref"],link["child_ref"]):link for link in exact}; matched=list(unique.values()); count=len(matched); maximum=obligation["max_count"]
        invalid=[link for link in attributed if link["resolution_status"]=="INVALID" or (link["resolution_status"]=="RESOLVED" and not _matches(obligation,link))]; unresolved=[link for link in attributed if link["resolution_status"]=="UNRESOLVED"]
        if count>=obligation["min_count"] and (maximum is None or count<=maximum):state="SATISFIED";reason=None
        elif maximum is not None and count>maximum:state="INVALID";reason="resolved semantic link cardinality exceeds max_count"
        elif invalid:state="INVALID";reason="explicit candidate has invalid type, direction, target, or resolution"
        elif unresolved:state="UNRESOLVED";reason="explicit candidate target is unresolved"
        else:state="MISSING";reason="required minimum cardinality is not satisfied"
        verdicts.append(ObligationVerdict(oid,obligation["required"],state,tuple(sorted(link["link_id"] for link in matched)),tuple(sorted(link["link_id"] for link in attributed)),obligation["min_count"],maximum,count,reason))
    return LinkCompletenessResult("SOLVED" if all((not item.required) or item.state=="SATISFIED" for item in verdicts) else "UNSOLVED",tuple(verdicts))
