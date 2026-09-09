from __future__ import annotations

import copy
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .call_resolution import resolve_function_calls
from .cw import ingest_cw
from .diagnostics import summarize_diagnostics
from .event_canonicalization import apply_canonical_event, approve_canonical_event, propose_canonical_event
from .event_logic import EventTriggerRule, detect_event_candidates
from .event_mapping import propose_event_mapping
from .identity import (
    CICIdentityError,
    canonical_file_key,
    canonical_file_ref,
    canonical_file_shard_path,
    canonical_function_ref,
    normalize_source_path,
    observed_file_ref,
)
from .modules.css import extract_css
from .modules.html import extract_html
from .modules.javascript import extract_javascript
from .modules.python import extract_python
from .modules.registry import extract as extract_language_ir
from .modules.registry import install_builtin_modules
from .reference_resolution import resolve_code_references
from .solver import SolverPolicy, run_solver

DEFAULT_EXCLUDED_DIRS=frozenset({".git",".hg",".svn","node_modules","__pycache__",".pytest_cache",".mypy_cache",".ruff_cache",".tox",".venv","venv","dist","build","target","bin","obj"})

@dataclass(frozen=True)
class ImportBundle:
    cw:dict[str,Any]
    ir:dict[str,Any]
    files_seen:int
    files_imported:int
    diagnostics:int

@dataclass(frozen=True)
class ImportResult:
    code_folder:Path
    cw_folder:Path
    cw_path:Path
    ir_path:Path
    files_seen:int
    files_imported:int
    diagnostics:int
    diagnostic_summary:dict[str,Any]
    shard_count:int


def _normalize_relative(path:Path,root:Path)->str: return normalize_source_path(path.relative_to(root).as_posix())

def _read_text(path:Path)->str|None:
    try: return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try: return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError: return None


def _walk_source_files(root:Path,excluded_dirs:frozenset[str])->list[Path]:
    files=[]
    for path in root.rglob("*"):
        parts=path.relative_to(root).parts
        if path.name in excluded_dirs or any(part in excluded_dirs for part in parts[:-1]): continue
        if path.is_file(): files.append(path)
    return sorted(files,key=lambda item:item.relative_to(root).as_posix().lower())


def _function_properties(file_record:dict[str,Any],symbols:list[dict[str,Any]])->list[dict[str,Any]]:
    properties=[]; source_path=file_record["path"]; owner_ref=file_record["canonical_file_ref"]
    def add(symbol,owner=None):
        name=symbol.get("name")
        if not isinstance(name,str) or not name: return
        qualified=symbol.get("qualified_name"); scoped=qualified if isinstance(qualified,str) and qualified else (f"{owner}.{name}" if owner else name)
        properties.append({"id":canonical_function_ref(source_path,scoped),"property_type_ref":"function","ruleset_ref":"RULESET_FUNCTION","status":"unlocked","value":{"function_type_ref":"implementation_function","properties":{"owner_file_ref":owner_ref,"source_file_ref":file_record["file_ref"],"source_path":source_path,"source_language":file_record["language_ir"].get("language_id","unclassified"),"name":name,"qualified_name":scoped,"owner":symbol.get("owner",owner),"async":bool(symbol.get("async")),"parameters":symbol.get("parameters",[]),"returns_annotation":symbol.get("returns_annotation"),"decorators":symbol.get("decorators",[]),"span":symbol.get("span"),"decomposition_state":symbol.get("decomposition_state","none")}}})
        for nested in symbol.get("nested_functions",[]):
            if isinstance(nested,dict): add(nested,scoped)
    for symbol in symbols:
        if not isinstance(symbol,dict): continue
        if symbol.get("kind")=="function": add(symbol)
        elif symbol.get("kind")=="class":
            owner=symbol.get("name") if isinstance(symbol.get("name"),str) else None
            for method in symbol.get("methods",[]):
                if isinstance(method,dict): add(method,owner)
    return properties


def _file_entity(file_record:dict[str,Any])->dict[str,Any]:
    source_path=file_record["path"]; lir=file_record["language_ir"]; ref=file_record["canonical_file_ref"]; key=file_record["canonical_file_key"]
    properties=[
        {"id":f"DATA::{ref}::SOURCE_PATH","property_type_ref":"data","ruleset_ref":"RULESET_DATA","status":"unlocked","value":{"data_type_ref":"source_path","value":source_path,"properties":{"provenance_only":True}}},
        {"id":f"DATA::{ref}::SOURCE_LANGUAGE","property_type_ref":"data","ruleset_ref":"RULESET_DATA","status":"unlocked","value":{"data_type_ref":"language_id","value":lir.get("language_id","unclassified"),"properties":{"provenance_only":True}}},
    ]
    properties.extend(_function_properties(file_record,lir.get("symbols",[])))
    return {"id":ref,"name":PurePosixPath(key).name,"entity_type_ref":"code","status":"unlocked","properties":properties,"required_links":[]}


def _cw_document(files:list[dict[str,Any]])->dict[str,Any]:
    return {
        "format":{"contract_format":"CANONICAL_CONTRACT","format_version":"2.1"},
        "identity":{"id":"CIC_IMPORTED_CODE_MODEL","name":"CIC Imported Code Model","type":"code_model","version":"0.4.0"},
        "status":"unlocked",
        "purpose":"Unbound CW candidate produced from deterministic source-code import. Specification selection and semantic validation happen after import.",
        "scope":{"owns":["active imported code model"],"does_not_own":["parser evidence archive","specification selection","semantic validation","renderer state"]},
        "entities":[_file_entity(item) for item in files],
        "constraints":{"invariants":[
            {"id":"CIC_ONE_FILE_ONE_ENTITY","rule":"Every imported source file maps to exactly one language-agnostic #FILE canonical Entity identity."},
            {"id":"CIC_SOURCE_SUFFIX_NOT_CANONICAL_IDENTITY","rule":"Source-format suffixes are provenance and MUST NOT appear in canonical #FILE identity or physical shard basename."},
            {"id":"CIC_ONE_FILE_ONE_SHARD","rule":"Every canonical #FILE Entity is serialized to exactly one FILE/<canonical path>.cw shard."},
            {"id":"CIC_FUNCTION_IS_FILE_PROPERTY","rule":"Functions and methods remain Properties of their owning #FILE Entity and never become Entities."},
            {"id":"CIC_NO_GUESSED_LINKS","rule":"Implementation import or call evidence does not become canonical Link truth without explicit resolution/authority."},
            {"id":"CIC_IMPORT_IS_SPEC_UNBOUND","rule":"Import MUST NOT select a CCF + NodeTypes + Rulesets interpretation bundle."},
        ]},
        "references":[],"gaps":[],"prose":{"summary":"CIC code import candidate; specification authority begins only after explicit validation binding."},
    }


def _materialize_event_candidates(cw:dict[str,Any],candidates:list[dict[str,Any]])->tuple[dict[str,Any],list[dict[str,Any]]]:
    result=cw; audit=[]
    for candidate in candidates:
        mapping=propose_event_mapping(result,candidate); proposal=propose_canonical_event(mapping); approved=approve_canonical_event(result,proposal); result=apply_canonical_event(result,approved)
        audit.append({"candidate_id":candidate.get("candidate_id"),"mapping_proposal_id":mapping.proposal_id,"event_property_ref":proposal.event_property["id"],"event_handler_link_ref":proposal.handler_link_property["id"],"target_function_ref":proposal.target_function_ref,"status":"MATERIALIZED","canonical_semantic_authority":False})
    return result,audit


def import_files(files:Iterable[dict[str,Any]],*,solver_policy:SolverPolicy|None=None,event_rules:Iterable[EventTriggerRule|dict[str,Any]]=(),materialize_events:bool=True)->ImportBundle:
    install_builtin_modules(python_extractor=extract_python,javascript_extractor=extract_javascript,html_extractor=extract_html,css_extractor=extract_css)
    normalized=[]; seen=set(); files_seen=0
    for item in files:
        files_seen+=1
        if not isinstance(item,dict): raise ValueError("CIC file entry must be an object")
        path=normalize_source_path(item.get("path")); content=item.get("content")
        if path in seen: raise ValueError(f"duplicate CIC source path: {path}")
        if not isinstance(content,str): raise ValueError(f"CIC source content must be text: {path}")
        seen.add(path); normalized.append({"path":path,"content":content})
    normalized.sort(key=lambda item:item["path"].lower())
    imported=[]; diagnostics=0; canonical_owners={}
    for item in normalized:
        lir=extract_language_ir(item["path"],item["content"]); diagnostics+=len(lir.get("diagnostics",[])); canonical_ref=canonical_file_ref(item["path"])
        previous=canonical_owners.get(canonical_ref)
        if previous is not None and previous!=item["path"]: raise CICIdentityError(f"canonical #FILE identity collision: {previous!r} and {item['path']!r} both map to {canonical_ref}")
        canonical_owners[canonical_ref]=item["path"]
        imported.append({"path":item["path"],"file_ref":observed_file_ref(item["path"]),"canonical_file_ref":canonical_ref,"canonical_file_key":canonical_file_key(item["path"]),"cw_shard_path":canonical_file_shard_path(canonical_ref),"language_ir":lir})
    ir={"kind":"cic_code_ir","version":"0.4.0","canonical_semantic_authority":False,"policy":{"maximum_extraction":True,"zero_semantic_guessing":True,"one_source_file_one_file_identity":True,"canonical_file_identity_is_language_agnostic":True,"source_suffix_is_not_canonical_identity":True,"function_is_file_property":True,"call_is_property_evidence":True,"event_requires_explicit_trigger_evidence":True,"solver_requires_explicit_opt_in":True,"import_selects_specification":False,"builtin_frontends":["python","javascript","html","css"]},"files":imported,"skipped_binary":[]}
    ir["diagnostic_summary"]=summarize_diagnostics(imported); ir["reference_evidence"]=resolve_code_references(ir); ir["call_evidence"]=resolve_function_calls(ir); ir["event_candidates"]=[asdict(candidate) for candidate in detect_event_candidates(ir,event_rules)]
    solved=run_solver(ir,policy=solver_policy); solved_ir=solved.ir; solved_ir["solver"]=solved.report(); cw=_cw_document(solved_ir.get("files",[]))
    if materialize_events: cw,event_materialization=_materialize_event_candidates(cw,solved_ir.get("event_candidates",[]))
    else: event_materialization=[]
    solved_ir["event_materialization"]=event_materialization
    return ImportBundle(cw,solved_ir,files_seen,len(imported),diagnostics)


def _manifest_document(cw,files):
    manifest=copy.deepcopy(cw); manifest["entities"]=[]; manifest["shards"]=[{"entity_ref":item["canonical_file_ref"],"artifact_ref":item["cw_shard_path"]} for item in sorted(files,key=lambda value:value["canonical_file_ref"].lower())]; manifest.setdefault("serialization",{}).update({"mode":"cw_entity_shards","one_entity_one_shard":True,"manifest":"model.cw","source_suffix_in_shard_name":False}); return manifest


def _write_sharded_cw(output_root:Path,bundle:ImportBundle)->tuple[Path,int]:
    files=[item for item in bundle.ir.get("files",[]) if isinstance(item,dict)]; entities={e["id"]:e for e in bundle.cw.get("entities",[]) if isinstance(e,dict) and isinstance(e.get("id"),str)}; manifest=_manifest_document(bundle.cw,files); cw_path=output_root/"model.cw"; cw_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    count=0
    for item in files:
        entity=entities.get(item["canonical_file_ref"])
        if entity is None: raise ValueError(f"CW shard entity missing from active model: {item['canonical_file_ref']}")
        shard=output_root/item["cw_shard_path"]; shard.parent.mkdir(parents=True,exist_ok=True); shard.write_text(json.dumps(entity,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); count+=1
    return cw_path,count


def import_folder(code_folder:str|Path,cw_folder:str|Path,*,excluded_dirs:frozenset[str]=DEFAULT_EXCLUDED_DIRS,solver_policy:SolverPolicy|None=None,event_rules:Iterable[EventTriggerRule|dict[str,Any]]=(),materialize_events:bool=True,force:bool=False)->ImportResult:
    source=Path(code_folder).expanduser().resolve(); output=Path(cw_folder).expanduser().resolve()
    if not source.is_dir(): raise ValueError(f"code folder not found: {source}")
    if source==output: raise ValueError("CW output folder must differ from code folder")
    if output in source.parents: raise ValueError(f"CW output folder cannot contain the code folder: {output}")
    if output.exists():
        if not output.is_dir(): raise ValueError(f"CW output path exists and is not a directory: {output}")
        if not force: raise ValueError(f"CW output folder already exists: {output}; use --force to replace it")
        shutil.rmtree(output)
    source_paths=_walk_source_files(source,excluded_dirs); text_files=[]; skipped=[]
    for path in source_paths:
        relative=_normalize_relative(path,source); content=_read_text(path)
        if content is None: skipped.append(relative)
        else: text_files.append({"path":relative,"content":content})
    bundle=import_files(text_files,solver_policy=solver_policy,event_rules=event_rules,materialize_events=materialize_events); bundle.ir["skipped_binary"]=skipped; output.mkdir(parents=True,exist_ok=False)
    try:
        ir_path=output/"import.ir.json"; ir_path.write_text(json.dumps(bundle.ir,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); cw_path,count=_write_sharded_cw(output,bundle); ingest_cw(output)
    except Exception:
        shutil.rmtree(output,ignore_errors=True); raise
    return ImportResult(source,output,cw_path,ir_path,len(source_paths),bundle.files_imported,bundle.diagnostics,dict(bundle.ir.get("diagnostic_summary",{})),count)
