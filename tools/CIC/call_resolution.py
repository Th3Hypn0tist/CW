from __future__ import annotations

from collections import defaultdict
from typing import Any

from .identity import canonical_file_ref, canonical_function_ref, observed_file_ref


class CallResolutionError(ValueError): pass


def _walk_function(symbol:dict[str,Any],path:str):
    qualified=symbol.get("qualified_name")
    if isinstance(qualified,str) and qualified:
        yield {"path":path,"name":symbol.get("name"),"owner":symbol.get("owner"),"qualified_name":qualified,"function_ref":canonical_function_ref(path,qualified),"parameters":symbol.get("parameters") if isinstance(symbol.get("parameters"),list) else [],"logic":symbol.get("logic") if isinstance(symbol.get("logic"),dict) else {}}
    for nested in symbol.get("nested_functions",[]):
        if isinstance(nested,dict): yield from _walk_function(nested,path)


def _inventory(ir):
    functions=[]; by_file=defaultdict(list)
    for record in ir.get("files",[]):
        if not isinstance(record,dict) or not isinstance(record.get("path"),str): continue
        path=record["path"]; lir=record.get("language_ir")
        if not isinstance(lir,dict): continue
        for symbol in lir.get("symbols",[]):
            if not isinstance(symbol,dict): continue
            if symbol.get("kind")=="function": items=list(_walk_function(symbol,path))
            elif symbol.get("kind")=="class": items=[item for method in symbol.get("methods",[]) if isinstance(method,dict) for item in _walk_function(method,path)]
            else: items=[]
            functions.extend(items); by_file[path].extend(items)
    return functions,by_file


def resolve_function_calls(ir:dict[str,Any])->list[dict[str,Any]]:
    if not isinstance(ir,dict) or not isinstance(ir.get("files"),list): raise CallResolutionError("CIC Code IR requires files array")
    functions,by_file=_inventory(ir); evidence=[]
    refs_by_source=defaultdict(list)
    for ref in ir.get("reference_evidence",[]):
        if isinstance(ref,dict) and isinstance(ref.get("provenance"),str): refs_by_source[ref["provenance"]].append(ref)
    for source in functions:
        calls=source.get("logic",{}).get("calls",[])
        if not isinstance(calls,list): continue
        for index,call in enumerate(calls):
            if not isinstance(call,dict): continue
            target=call.get("target") if isinstance(call.get("target"),str) else None; candidates=[]
            if target:
                direct=[fn for fn in by_file.get(source["path"],[]) if fn["qualified_name"]==target or fn["qualified_name"]==f"{source['qualified_name']}.<locals>.{target}"]
                candidates.extend(direct)
                if "." not in target:
                    for ref in refs_by_source.get(source["path"],[]):
                        if ref.get("resolution_status")!="RESOLVED": continue
                        target_ref=ref.get("target_entity_ref")
                        if not isinstance(target_ref,str) or not target_ref.startswith("FILE::"): continue
                        target_path=target_ref.removeprefix("FILE::")
                        candidates.extend(fn for fn in by_file.get(target_path,[]) if fn["qualified_name"]==target)
            unique={item["function_ref"]:item for item in candidates}
            candidates=list(unique.values())
            if len(candidates)==1: status="RESOLVED"; reason="EXACT_FUNCTION_SURFACE"; resolved=candidates[0]
            elif len(candidates)>1: status="UNRESOLVED"; reason="AMBIGUOUS_FUNCTION_SURFACE"; resolved=None
            else: status="UNRESOLVED"; reason="NO_PROVEN_FUNCTION_SURFACE"; resolved=None
            span=call.get("span") if isinstance(call.get("span"),dict) else {}
            evidence.append({"call_id":f"CALL::{source['path']}::{source['qualified_name']}::{index}","source_file_ref":observed_file_ref(source["path"]),"source_canonical_file_ref":canonical_file_ref(source["path"]),"source_function_ref":source["function_ref"],"target_file_ref":observed_file_ref(resolved["path"]) if resolved else None,"target_canonical_file_ref":canonical_file_ref(resolved["path"]) if resolved else None,"target_function_ref":resolved["function_ref"] if resolved else None,"target_expression":target,"resolution_status":status,"resolution_reason":reason,"candidate_function_refs":[item["function_ref"] for item in candidates],"function_property_scope":"#FILE","function_refs_are_property_refs":True,"canonical_link_status":"UNRESOLVED","canonical_semantic_authority":False,"line":span.get("line"),"provenance":source["path"],"evidence_kind":"implementation_function_call","cic_ir":dict(call)})
    return evidence
