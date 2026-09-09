from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

TIMESTAMP_RE = re.compile(r"^\d{14}$")
HASH_RE = re.compile(r"^[0-9a-f]{32}$")


def serialize_entity(entity: dict[str, Any]) -> str:
    return json.dumps(entity, indent=2, ensure_ascii=False) + "\n"


def calculate_entity_hash(entity: dict[str, Any]) -> str:
    candidate = copy.deepcopy(entity)
    candidate["hash"] = ""
    return hashlib.md5(serialize_entity(candidate).encode("utf-8")).hexdigest()


def validate_entity_version(entity: dict[str, Any]) -> str | None:
    """Return an error message for an invalid optional Node version stamp."""
    timestamp = entity.get("timestamp")
    stored_hash = entity.get("hash")
    if timestamp is None and stored_hash is None:
        return None
    if timestamp is None or stored_hash is None:
        return "version stamp requires both timestamp and hash"
    if not isinstance(timestamp, str) or not TIMESTAMP_RE.fullmatch(timestamp):
        return "timestamp must use YYYYMMDDhhmmss"
    if not isinstance(stored_hash, str) or not HASH_RE.fullmatch(stored_hash):
        return "hash must be lowercase MD5 hex"
    calculated = calculate_entity_hash(entity)
    if calculated != stored_hash:
        return f"version hash mismatch: stored {stored_hash}, calculated {calculated}"
    return None
