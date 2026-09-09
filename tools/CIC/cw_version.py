from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from .cw import CWValidationError, validate_cw

TIMESTAMP_RE=re.compile(r"^\d{14}$")
HASH_RE=re.compile(r"^[0-9a-f]{32}$")
VERSION_FIELDS=frozenset({"timestamp","hash"})


def serialize_entity(entity:dict[str,Any])->str: return json.dumps(entity,indent=2,ensure_ascii=False)+"\n"

def versionless_entity(entity:dict[str,Any])->dict[str,Any]:
    candidate=copy.deepcopy(entity)
    for field in VERSION_FIELDS: candidate.pop(field,None)
    return candidate

def has_entity_version(entity:dict[str,Any])->bool: return isinstance(entity.get("timestamp"),str) and isinstance(entity.get("hash"),str)
def same_entity_payload(left:dict[str,Any],right:dict[str,Any])->bool: return versionless_entity(left)==versionless_entity(right)
def calculate_entity_hash(entity:dict[str,Any])->str:
    candidate=copy.deepcopy(entity); candidate["hash"]=""; return hashlib.md5(serialize_entity(candidate).encode("utf-8")).hexdigest()
def _timestamp_now()->str: return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

def stamp_entity_version(entity:dict[str,Any],*,timestamp:str|None=None)->dict[str,Any]:
    value=timestamp or _timestamp_now()
    if not TIMESTAMP_RE.fullmatch(value): raise CWValidationError("CW version timestamp must use YYYYMMDDhhmmss")
    stamped=copy.deepcopy(entity); stamped["timestamp"]=value; stamped["hash"]=""; stamped["hash"]=calculate_entity_hash(stamped); return stamped

def verify_entity_version(entity:dict[str,Any])->None:
    timestamp=entity.get("timestamp"); stored=entity.get("hash")
    if timestamp is None and stored is None: return
    if timestamp is None or stored is None: raise CWValidationError(f"CW Entity {entity.get('id')!r} version stamp requires both timestamp and hash")
    if not isinstance(timestamp,str) or not TIMESTAMP_RE.fullmatch(timestamp): raise CWValidationError(f"CW Entity {entity.get('id')!r} timestamp must use YYYYMMDDhhmmss")
    if not isinstance(stored,str) or not HASH_RE.fullmatch(stored): raise CWValidationError(f"CW Entity {entity.get('id')!r} hash must be lowercase MD5 hex")
    calculated=calculate_entity_hash(entity)
    if calculated!=stored: raise CWValidationError(f"CW Entity version hash mismatch: {entity.get('id')!r}; stored {stored}, calculated {calculated}")
def verify_cw_versions(document:dict[str,Any])->dict[str,Any]:
    validate_cw(document)
    for entity in document.get("entities",[]):
        if isinstance(entity,dict): verify_entity_version(entity)
    return document

def finalize_cw_for_write(document:dict[str,Any],*,changed_entity_refs:Iterable[str]|None=None,timestamp:str|None=None)->dict[str,Any]:
    validate_cw(document); finalized=copy.deepcopy(document); selected=None if changed_entity_refs is None else set(changed_entity_refs); known={e.get("id") for e in finalized.get("entities",[]) if isinstance(e,dict) and isinstance(e.get("id"),str)}
    if selected is not None:
        unknown=selected-known
        if unknown: raise CWValidationError(f"CW version update refers to unknown Entity ids: {sorted(unknown)}")
    version_time=timestamp or _timestamp_now()
    for index,entity in enumerate(finalized.get("entities",[])):
        if isinstance(entity,dict) and (selected is None or entity.get("id") in selected): finalized["entities"][index]=stamp_entity_version(entity,timestamp=version_time)
    verify_cw_versions(finalized); return finalized
