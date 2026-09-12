from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from CIC.cw import CWValidationError, validate_cw


TIMESTAMP_RE = re.compile(r"^\d{14}$")
HASH_RE = re.compile(r"^[0-9a-f]{32}$")
VERSION_FIELDS = frozenset({"timestamp", "hash"})
_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"


def serialize_entity(entity: dict[str, Any]) -> str:
    """Serialize one direct CW Entity exactly like a CIC .cw shard."""
    return json.dumps(entity, indent=2, ensure_ascii=False) + "\n"


def versionless_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Return the Node payload used to decide whether a new version is required."""
    candidate = copy.deepcopy(entity)
    for field in VERSION_FIELDS:
        candidate.pop(field, None)
    return candidate


def has_entity_version(entity: dict[str, Any]) -> bool:
    return isinstance(entity.get("timestamp"), str) and isinstance(entity.get("hash"), str)


def same_entity_payload(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Compare canonical Node payloads without operational version metadata."""
    return versionless_entity(left) == versionless_entity(right)


def calculate_entity_hash(entity: dict[str, Any]) -> str:
    """Return the MD5 version checksum with Entity.hash forced to an empty string."""
    candidate = copy.deepcopy(entity)
    candidate["hash"] = ""
    payload = serialize_entity(candidate).encode("utf-8")
    return hashlib.md5(payload).hexdigest()


def _timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)


def next_version_timestamp(previous_timestamps: Iterable[str], *, now: str | None = None) -> str:
    """Return a timestamp strictly newer than every supplied previous version.

    CW Node timestamps have one-second resolution. A real change can therefore
    occur inside the same wall-clock second as the previous version. In that
    case, advance the version clock by one second instead of collapsing two
    distinct versions onto the same timestamp/hash pair.
    """
    current = now or _timestamp_now()
    if not TIMESTAMP_RE.fullmatch(current):
        raise CWValidationError("CW version timestamp must use YYYYMMDDhhmmss")
    candidate = datetime.strptime(current, _TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    for value in previous_timestamps:
        if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
            raise CWValidationError(f"invalid previous CW version timestamp: {value!r}")
        previous = datetime.strptime(value, _TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
        if candidate <= previous:
            candidate = previous + timedelta(seconds=1)
    return candidate.strftime(_TIMESTAMP_FORMAT)


def stamp_entity_version(entity: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    """Stamp a new Entity version after its containing CW has already validated."""
    value = timestamp or _timestamp_now()
    if not TIMESTAMP_RE.fullmatch(value):
        raise CWValidationError("CW version timestamp must use YYYYMMDDhhmmss")
    stamped = copy.deepcopy(entity)
    stamped["timestamp"] = value
    stamped["hash"] = ""
    stamped["hash"] = calculate_entity_hash(stamped)
    return stamped


def verify_entity_version(entity: dict[str, Any]) -> None:
    """Verify an Entity version by recalculating MD5 with hash set to an empty string."""
    timestamp = entity.get("timestamp")
    stored_hash = entity.get("hash")
    if timestamp is None and stored_hash is None:
        return
    if timestamp is None or stored_hash is None:
        raise CWValidationError(f"CW Entity {entity.get('id')!r} version stamp requires both timestamp and hash")
    if not isinstance(timestamp, str) or not TIMESTAMP_RE.fullmatch(timestamp):
        raise CWValidationError(f"CW Entity {entity.get('id')!r} timestamp must use YYYYMMDDhhmmss")
    if not isinstance(stored_hash, str) or not HASH_RE.fullmatch(stored_hash):
        raise CWValidationError(f"CW Entity {entity.get('id')!r} hash must be lowercase MD5 hex")
    calculated = calculate_entity_hash(entity)
    if calculated != stored_hash:
        raise CWValidationError(
            f"CW Entity version hash mismatch: {entity.get('id')!r}; stored {stored_hash}, calculated {calculated}"
        )


def verify_cw_versions(document: dict[str, Any]) -> dict[str, Any]:
    """Verify all versioned Entities in an already valid CW document."""
    validate_cw(document)
    for entity in document.get("entities", []):
        if isinstance(entity, dict):
            verify_entity_version(entity)
    return document


def finalize_cw_for_write(
    document: dict[str, Any],
    *,
    changed_entity_refs: Iterable[str] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Validate first, then timestamp+hash only the Entities being created or updated.

    changed_entity_refs=None means every Entity is new and receives a version stamp.
    Supplying refs lets an update path preserve unchanged Entity versions.
    """
    validate_cw(document)
    finalized = copy.deepcopy(document)
    selected = None if changed_entity_refs is None else set(changed_entity_refs)
    known = {
        entity.get("id")
        for entity in finalized.get("entities", [])
        if isinstance(entity, dict) and isinstance(entity.get("id"), str)
    }
    if selected is not None:
        unknown = selected - known
        if unknown:
            raise CWValidationError(f"CW version update refers to unknown Entity ids: {sorted(unknown)}")

    version_time = timestamp or _timestamp_now()
    for index, entity in enumerate(finalized.get("entities", [])):
        if not isinstance(entity, dict):
            continue
        if selected is None or entity.get("id") in selected:
            finalized["entities"][index] = stamp_entity_version(entity, timestamp=version_time)

    verify_cw_versions(finalized)
    return finalized
