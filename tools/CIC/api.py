from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import api_core as _core
from .api_core import ImportBundle, ImportResult
from .cw import ingest_cw
from .cw_version import finalize_cw_for_write, has_entity_version, same_entity_payload, serialize_entity, verify_cw_versions

class ToolchainValidationError(ValueError): pass

DEFAULT_EXCLUDED_DIRS=_core.DEFAULT_EXCLUDED_DIRS
import_files=_core.import_files
_normalize_relative=_core._normalize_relative
_read_text=_core._read_text
_walk_source_files=_core._walk_source_files


def _is_cw_root(path:Path)->bool:
    return (path/"linter"/"cw_spec_lint.py").is_file() and (path/"linter"/"cw_validate.py").is_file() and (path/"spec_sets").is_dir()
def resolve_cw_root(value:str|Path|None=None)->Path:
    if value is not None:
        root=Path(value).expanduser().resolve()
        if not _is_cw_root(root): raise ToolchainValidationError(f"CW root does not contain required linter/spec toolchain: {root}")
        return root
    if os.environ.get("CW_ROOT"):
        root=Path(os.environ["CW_ROOT"]).expanduser().resolve()
        if not _is_cw_root(root): raise ToolchainValidationError(f"CW_ROOT does not contain required linter/spec toolchain: {root}")
        return root
    for parent in Path(__file__).resolve().parents:
        if _is_cw_root(parent): return parent
    raise ToolchainValidationError("CW toolchain root not found; provide cw_root or CW_ROOT")
def _selected_spec_set(root:Path,spec_set:str|Path|None)->Path:
    candidate=Path(spec_set).expanduser().resolve() if spec_set is not None else root/"spec_sets"/"CW_CORE_v1.1.0.json"
    if not candidate.is_file(): raise ToolchainValidationError(f"CW specification set not found: {candidate}")
    return candidate
def _evaluation_ref(spec_set:Path)->str:
    try: manifest=json.loads(spec_set.read_text(encoding="utf-8"))
    except Exception as exc: raise ToolchainValidationError(f"cannot read specification set: {spec_set}: {exc}") from exc
    identity=manifest.get("id"); version=manifest.get("version")
    if not isinstance(identity,str) or not identity or not isinstance(version,str) or not version: raise ToolchainValidationError(f"specification set lacks id/version: {spec_set}")
    return f"{identity}@{version}"
def _run(root:Path,script:str,args:list[str])->tuple[int,str,str]:
    completed=subprocess.run([sys.executable,str(root/"linter"/script),*args],cwd=root,text=True,capture_output=True,check=False); return completed.returncode,completed.stdout,completed.stderr

def validate_toolchain(*,cw_root:str|Path|None=None,spec_set:str|Path|None=None)->dict[str,Any]:
    root=resolve_cw_root(cw_root); selected=_selected_spec_set(root,spec_set)
    cic_root=Path(__file__).resolve().parent
    compile_targets=[*sorted(cic_root.glob("*.py")),*sorted((cic_root/"modules").glob("*.py")),root/"linter"/"__init__.py",root/"linter"/"cw_spec_common.py",root/"linter"/"cw_spec_lint.py",root/"linter"/"cw_compose.py",root/"linter"/"cw_bind.py",root/"linter"/"cw_version.py",root/"linter"/"cw_validate.py"]
    completed=subprocess.run([sys.executable,"-m","py_compile",*(str(path) for path in compile_targets)],cwd=root,text=True,capture_output=True,check=False)
    if completed.returncode!=0: raise ToolchainValidationError("CW/CIC tool compile validation failed:\n"+(completed.stderr or completed.stdout))
    code,stdout,stderr=_run(root,"cw_spec_lint.py",["--spec-set",str(selected),"--coverage","--json"])
    if code!=0: raise ToolchainValidationError("CW specification/tool validation failed:\n"+(stderr or stdout))
    try: return json.loads(stdout)
    except json.JSONDecodeError as exc: raise ToolchainValidationError(f"CW spec linter returned invalid JSON: {exc}") from exc

def _validation_projection(cw_folder:Path,spec_set:Path)->dict[str,Any]:
    document=copy.deepcopy(ingest_cw(cw_folder)); document.pop("shards",None); document.pop("serialization",None); document["specification_ref"]=_evaluation_ref(spec_set); return document

def _semantic_validate(cw_folder:Path,*,cw_root:Path,spec_set:Path)->str:
    document=_validation_projection(cw_folder,spec_set)
    with tempfile.TemporaryDirectory(prefix="cw-cic-validate-") as tmp:
        candidate=Path(tmp)/"candidate.cw"; candidate.write_text(json.dumps(document,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); code,stdout,stderr=_run(cw_root,"cw_validate.py",[str(candidate),"--spec-set",str(spec_set),"--json"])
    if code!=0: raise ToolchainValidationError("generated CW failed semantic validation:\n"+(stderr or stdout))
    try: report=json.loads(stdout)
    except json.JSONDecodeError as exc: raise ToolchainValidationError(f"CW validator returned invalid JSON: {exc}") from exc
    result=report.get("result")
    if result not in {"READY","UNREADY"}: raise ToolchainValidationError(f"generated CW did not reach a valid model state: {result!r}")
    return str(result)
def _entities_by_id(document): return {e["id"]:e for e in document.get("entities",[]) if isinstance(e,dict) and isinstance(e.get("id"),str)}
def _write_finalized_shards(cw_folder:Path,finalized:dict[str,Any])->None:
    entities=_entities_by_id(finalized); manifest=json.loads((cw_folder/"model.cw").read_text(encoding="utf-8"))
    for record in manifest.get("shards",[]):
        if not isinstance(record,dict): continue
        entity=entities.get(record.get("entity_ref")); artifact=record.get("artifact_ref")
        if entity is None or not isinstance(artifact,str): raise ToolchainValidationError(f"CW version finalization cannot resolve shard: {record!r}")
        (cw_folder/Path(artifact)).write_text(serialize_entity(entity),encoding="utf-8")
    verify_cw_versions(ingest_cw(cw_folder))
def _finalize_created(cw_folder): _write_finalized_shards(cw_folder,finalize_cw_for_write(ingest_cw(cw_folder)))
def _finalize_updated(cw_folder,previous):
    verify_cw_versions(previous); candidate=ingest_cw(cw_folder); prior=_entities_by_id(previous); reconciled=copy.deepcopy(candidate); changed=set()
    for index,entity in enumerate(reconciled.get("entities",[])):
        if not isinstance(entity,dict) or not isinstance(entity.get("id"),str): continue
        old=prior.get(entity["id"])
        if old is not None and has_entity_version(old) and same_entity_payload(old,entity): reconciled["entities"][index]=copy.deepcopy(old)
        else: changed.add(entity["id"])
    _write_finalized_shards(cw_folder,finalize_cw_for_write(reconciled,changed_entity_refs=changed))
def _transaction_paths(target):
    token=uuid.uuid4().hex; return target.with_name(f".{target.name}.cic-new-{token}"),target.with_name(f".{target.name}.cic-old-{token}")
def _retarget(result,target): return replace(result,cw_folder=target,cw_path=target/result.cw_path.relative_to(result.cw_folder),ir_path=target/result.ir_path.relative_to(result.cw_folder))

def import_folder(code_folder:str|Path,cw_folder:str|Path,*,force:bool=False,cw_root:str|Path|None=None,spec_set:str|Path|None=None,validate_tools:bool=True,**kwargs:Any)->ImportResult:
    source=Path(code_folder).expanduser().resolve(); target=Path(cw_folder).expanduser().resolve()
    if not source.is_dir(): raise ValueError(f"code folder not found: {source}")
    if source==target: raise ValueError("CW output folder must differ from code folder")
    if target in source.parents: raise ValueError(f"CW output folder cannot contain the code folder: {target}")
    if source in target.parents: raise ValueError(f"CW output folder cannot be inside the code folder: {target}")
    if target.exists() and not target.is_dir(): raise ValueError(f"CW output path exists and is not a directory: {target}")
    if target.exists() and not force: raise ValueError(f"CW output folder already exists: {target}; use --force to update it")

    root=resolve_cw_root(cw_root); selected=_selected_spec_set(root,spec_set)
    if validate_tools: validate_toolchain(cw_root=root,spec_set=selected)

    staged,backup=_transaction_paths(target); previous=None
    if target.exists(): previous=ingest_cw(target); verify_cw_versions(previous)
    result=None
    try:
        result=_core.import_folder(source,staged,force=False,**kwargs)
        _semantic_validate(staged,cw_root=root,spec_set=selected)
        _finalize_created(staged) if previous is None else _finalize_updated(staged,previous)
        verify_cw_versions(ingest_cw(staged)); _semantic_validate(staged,cw_root=root,spec_set=selected)
        if previous is None: staged.rename(target)
        else:
            target.rename(backup)
            try: staged.rename(target)
            except Exception: backup.rename(target); raise
            shutil.rmtree(backup,ignore_errors=True)
    except Exception:
        shutil.rmtree(staged,ignore_errors=True)
        if backup.exists() and not target.exists(): backup.rename(target)
        raise
    if result is None: raise RuntimeError("CIC import completed without ImportResult")
    return _retarget(result,target)
