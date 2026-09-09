from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .identity import canonical_file_ref, observed_file_ref


class ReferenceResolutionError(ValueError):
    pass


def _module_candidates(base: PurePosixPath) -> tuple[str,str]:
    text=str(base); return (f"{text}.py",f"{text}/__init__.py")


def _python_import_base(source_path:str,record:dict[str,Any])->PurePosixPath|None:
    kind=record.get("kind")
    if kind=="import":
        module=record.get("module"); return PurePosixPath(*module.split(".")) if isinstance(module,str) and module else None
    if kind!="from_import": return None
    module=record.get("module") or ""; level=record.get("level",0)
    if not isinstance(module,str) or not isinstance(level,int) or level<0: return None
    parts=[p for p in module.split(".") if p]
    if level==0: return PurePosixPath(*parts) if parts else None
    base=PurePosixPath(source_path).parent
    for _ in range(level-1):
        if str(base) in {"","."}: return None
        base=base.parent
    return base.joinpath(*parts) if parts else base

_JS_TS_SUFFIXES=(".js",".mjs",".cjs",".jsx",".ts",".tsx")

def _lexical_relative_path(source_path:str,reference:str)->PurePosixPath|None:
    if not(reference.startswith("./") or reference.startswith("../")): return None
    parts=list(PurePosixPath(source_path).parent.parts)
    for part in reference.replace("\\","/").split("/"):
        if part in {"","."}: continue
        if part=="..":
            if not parts: return None
            parts.pop()
        else: parts.append(part)
    return PurePosixPath(*parts) if parts else None


def _js_ts_candidates(source_path:str,record:dict[str,Any])->tuple[tuple[str,...],str|None]:
    reference=record.get("module")
    if not isinstance(reference,str) or not reference: return (),None
    base=_lexical_relative_path(source_path,reference)
    if base is None: return (),"EXTERNAL_OR_UNPROVEN_REFERENCE"
    if base.suffix: return (str(base),),None
    text=str(base); return tuple([f"{text}{s}" for s in _JS_TS_SUFFIXES]+[f"{text}/index{s}" for s in _JS_TS_SUFFIXES]),None


def resolve_code_references(ir:dict[str,Any])->list[dict[str,Any]]:
    if not isinstance(ir,dict) or not isinstance(ir.get("files"),list): raise ReferenceResolutionError("CIC Code IR requires files array")
    available={item["path"] for item in ir["files"] if isinstance(item,dict) and isinstance(item.get("path"),str)}
    evidence=[]
    for file_record in ir["files"]:
        if not isinstance(file_record,dict): continue
        source_path=file_record.get("path"); language_ir=file_record.get("language_ir")
        if not isinstance(source_path,str) or not isinstance(language_ir,dict): continue
        language_id=language_ir.get("language_id"); imports=language_ir.get("imports",[])
        if not isinstance(imports,list): raise ReferenceResolutionError(f"imports must be an array: {source_path}")
        for index,record in enumerate(imports):
            if not isinstance(record,dict): raise ReferenceResolutionError(f"import evidence must be an object: {source_path}")
            target_reference=record.get("module"); span=record.get("span") if isinstance(record.get("span"),dict) else {}
            candidates=(); forced=None; resolved_reason="EXACT_LOCAL_MODULE"; ambiguous_reason="AMBIGUOUS_LOCAL_TARGET"
            if language_id=="python":
                base=_python_import_base(source_path,record); candidates=_module_candidates(base) if base is not None and str(base) not in {"","."} else ()
            elif language_id in {"javascript","typescript"}:
                candidates,forced=_js_ts_candidates(source_path,record); resolved_reason="EXACT_LOCAL_RELATIVE_MODULE"; ambiguous_reason="AMBIGUOUS_LOCAL_RELATIVE_MODULE"
            matches=tuple(c for c in candidates if c in available)
            if forced: status="UNRESOLVED"; reason=forced; target=None
            elif len(matches)==1: status="RESOLVED"; reason=resolved_reason; target=matches[0]
            elif len(matches)>1: status="UNRESOLVED"; reason=ambiguous_reason; target=None
            else: status="UNRESOLVED"; reason="NO_PROVEN_LOCAL_TARGET"; target=None
            evidence.append({"evidence_id":f"IMPORT::{source_path}::{index}","source_entity_ref":observed_file_ref(source_path),"target_entity_ref":observed_file_ref(target) if target else None,"source_canonical_entity_ref":canonical_file_ref(source_path),"target_canonical_entity_ref":canonical_file_ref(target) if target else None,"target_reference":target_reference,"resolution_status":status,"resolution_reason":reason,"candidate_paths":list(candidates),"matched_paths":list(matches),"import_kind":record.get("kind"),"line":span.get("line"),"provenance":source_path,"evidence_kind":"implementation_import","observed_identity_preserves_source_suffix":True,"canonical_identity_is_language_agnostic":True,"canonical_dependency_status":"UNRESOLVED","canonical_semantic_authority":False,"cic_ir":dict(record)})
    return evidence
