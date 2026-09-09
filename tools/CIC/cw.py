from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
from typing import Any

from CIC.identity import canonical_file_key_from_ref


class CWValidationError(ValueError):
    pass


CW_EXTENSION = ".cw"
JSON_EXTENSION = ".json"
MONOLITHIC_EXTENSIONS = frozenset({CW_EXTENSION, JSON_EXTENSION})
CW_FOLDER_ENTRY = "model.cw"


def _parse_cw_json_text(content: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CWValidationError(f"invalid CW JSON serialization in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise CWValidationError(f"CW root must be an object: {label}")
    return value


def _read_serialized_object(candidate: Path, *, allowed_extensions: frozenset[str]) -> dict[str, Any]:
    if not candidate.is_file():
        raise CWValidationError(f"CW input not found: {candidate}")
    suffix = candidate.suffix.lower()
    if suffix not in allowed_extensions:
        allowed = " or ".join(sorted(allowed_extensions))
        raise CWValidationError(f"CW input must use {allowed} extension: {candidate}")
    return _parse_cw_json_text(candidate.read_text(encoding="utf-8"), str(candidate))


def _read_cw_shard(candidate: Path) -> dict[str, Any]:
    return _read_serialized_object(candidate, allowed_extensions=frozenset({CW_EXTENSION}))


def _normalize_artifact_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CWValidationError("CW shard artifact_ref must be a non-empty string")
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CWValidationError(f"invalid CW shard artifact_ref: {value!r}")
    if path.suffix.lower() != CW_EXTENSION:
        raise CWValidationError(f"CW shard must use {CW_EXTENSION} extension: {value!r}")
    return str(path)


def _validated_manifest_record(record: Any) -> tuple[str, str]:
    if not isinstance(record, dict):
        raise CWValidationError("CW shard manifest entry must be an object")
    entity_ref = record.get("entity_ref")
    artifact_ref = record.get("artifact_ref")
    if not isinstance(entity_ref, str) or not entity_ref:
        raise CWValidationError(f"CW shard entity_ref missing: {entity_ref!r}")
    return entity_ref, _normalize_artifact_ref(artifact_ref)


def _validate_direct_entity_shard(shard: dict[str, Any], entity_ref: str, artifact_ref: str) -> dict[str, Any]:
    if isinstance(shard.get("format"), dict) or "entities" in shard:
        raise CWValidationError(f"CW shard must be one direct canonical Entity, not a contract wrapper: {artifact_ref}")
    shard_id = shard.get("id")
    if not isinstance(shard_id, str) or not shard_id:
        raise CWValidationError(f"CW shard Entity id missing: {artifact_ref}")
    if shard_id != entity_ref:
        raise CWValidationError(f"CW shard identity mismatch: manifest {entity_ref!r}, shard {shard_id!r}")
    if not isinstance(shard.get("properties"), list):
        raise CWValidationError(f"CW shard Entity properties must be an array: {artifact_ref}")
    return shard


def _compose_manifest(manifest: dict[str, Any], shard_loader) -> dict[str, Any]:
    shards = manifest.get("shards")
    if shards is None:
        return manifest
    if not isinstance(shards, list):
        raise CWValidationError("CW manifest shards must be an array")
    inline_entities = manifest.get("entities")
    if not isinstance(inline_entities, list):
        raise CWValidationError("sharded CW manifest entities must be an array")
    if inline_entities:
        raise CWValidationError("sharded CW manifest must not duplicate inline Entity definitions")

    entities: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    seen_artifacts: set[str] = set()
    for record in shards:
        entity_ref, artifact_ref = _validated_manifest_record(record)
        if artifact_ref in seen_artifacts:
            raise CWValidationError(f"duplicate CW shard artifact_ref: {artifact_ref}")
        seen_artifacts.add(artifact_ref)
        shard = shard_loader(artifact_ref)
        entity = _validate_direct_entity_shard(shard, entity_ref, artifact_ref)
        if entity_ref in seen_entities:
            raise CWValidationError(f"duplicate canonical shard Entity: {entity_ref}")
        seen_entities.add(entity_ref)
        entities.append(copy.deepcopy(entity))

    assembled = copy.deepcopy(manifest)
    assembled["entities"] = entities
    assembled.setdefault("serialization", {})["assembled_from_shards"] = True
    return assembled


def _assemble_sharded_model(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("shards") is not None and manifest_path.suffix.lower() != CW_EXTENSION:
        raise CWValidationError("sharded CW requires model.cw and .cw Entity shards; .json is monolithic-only")
    root = manifest_path.parent.resolve()

    def load_shard(artifact_ref: str) -> dict[str, Any]:
        relative = PurePosixPath(artifact_ref)
        shard_path = (root / Path(*relative.parts)).resolve()
        if shard_path == root or root not in shard_path.parents:
            raise CWValidationError(f"CW shard escapes model folder: {artifact_ref}")
        return _read_cw_shard(shard_path)

    return _compose_manifest(manifest, load_shard)


def _normalize_uploaded_path(value: Any, *, allowed_extensions: frozenset[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CWValidationError("CW upload path must be a non-empty string")
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CWValidationError(f"invalid CW upload path: {value!r}")
    if path.suffix.lower() not in allowed_extensions:
        allowed = " or ".join(sorted(allowed_extensions))
        raise CWValidationError(f"CW ingress accepts only {allowed} artifacts: {value}")
    return str(path)


def ingest_cw_files(files: Any) -> dict[str, Any]:
    if not isinstance(files, list) or not files:
        raise CWValidationError("CW ingress requires a non-empty files array")
    if len(files) == 1:
        item = files[0]
        if not isinstance(item, dict):
            raise CWValidationError("CW upload entry must be an object")
        path = _normalize_uploaded_path(item.get("path"), allowed_extensions=MONOLITHIC_EXTENSIONS)
        content = item.get("content")
        if not isinstance(content, str):
            raise CWValidationError(f"CW artifact content must be text: {path}")
        document = _parse_cw_json_text(content, path)
        if document.get("shards") is not None and PurePosixPath(path).suffix.lower() == JSON_EXTENSION:
            raise CWValidationError(".json CW input is monolithic-only and must not declare shards")
        if document.get("shards") is None:
            return validate_cw(document)
        if PurePosixPath(path).name != CW_FOLDER_ENTRY:
            raise CWValidationError(f"sharded CW upload requires {CW_FOLDER_ENTRY}")
        raise CWValidationError("sharded CW upload is missing declared .cw Entity shards")

    uploaded: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict):
            raise CWValidationError("CW upload entry must be an object")
        path = _normalize_uploaded_path(item.get("path"), allowed_extensions=frozenset({CW_EXTENSION}))
        content = item.get("content")
        if not isinstance(content, str):
            raise CWValidationError(f"CW artifact content must be text: {path}")
        if path in uploaded:
            raise CWValidationError(f"duplicate CW upload path: {path}")
        uploaded[path] = content

    manifest_paths = [path for path in uploaded if PurePosixPath(path).name == CW_FOLDER_ENTRY]
    if len(manifest_paths) != 1:
        raise CWValidationError(f"sharded CW upload must contain exactly one {CW_FOLDER_ENTRY}; found {len(manifest_paths)}")
    manifest_path = PurePosixPath(manifest_paths[0])
    root = manifest_path.parent
    manifest = _parse_cw_json_text(uploaded[str(manifest_path)], str(manifest_path))
    required_paths: set[str] = {str(manifest_path)}

    def load_shard(artifact_ref: str) -> dict[str, Any]:
        upload_path = str(root / PurePosixPath(artifact_ref)) if str(root) != "." else artifact_ref
        required_paths.add(upload_path)
        content = uploaded.get(upload_path)
        if content is None:
            raise CWValidationError(f"CW shard missing from upload: {artifact_ref}")
        return _parse_cw_json_text(content, upload_path)

    assembled = _compose_manifest(manifest, load_shard)
    extras = sorted(set(uploaded) - required_paths)
    if extras:
        raise CWValidationError(f"CW upload contains artifacts outside the manifest closure: {extras}")
    return validate_cw(assembled)


def load_cw(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / CW_FOLDER_ENTRY
        manifest = _read_serialized_object(candidate, allowed_extensions=frozenset({CW_EXTENSION}))
        return _assemble_sharded_model(candidate, manifest)
    suffix = candidate.suffix.lower()
    if suffix not in MONOLITHIC_EXTENSIONS:
        raise CWValidationError(f"CW input must use .cw or .json extension: {candidate}")
    manifest = _read_serialized_object(candidate, allowed_extensions=MONOLITHIC_EXTENSIONS)
    if suffix == JSON_EXTENSION and manifest.get("shards") is not None:
        raise CWValidationError(".json CW input is monolithic-only and must not declare shards")
    return _assemble_sharded_model(candidate, manifest)


def validate_cw(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise CWValidationError("CW document must be an object")
    if not isinstance(document.get("format"), dict):
        raise CWValidationError("CW format block missing")
    identity = document.get("identity")
    if not isinstance(identity, dict) or not isinstance(identity.get("id"), str) or not identity.get("id"):
        raise CWValidationError("CW identity.id missing")
    specification_ref = document.get("specification_ref")
    if specification_ref is not None and (not isinstance(specification_ref, str) or not specification_ref.strip()):
        raise CWValidationError("CW specification_ref must be a non-empty string when bound")
    entities = document.get("entities")
    if not isinstance(entities, list):
        raise CWValidationError("CW entities must be an array")

    identities: set[str] = set()
    for entity in entities:
        if not isinstance(entity, dict):
            raise CWValidationError("CW entity must be an object")
        entity_id = entity.get("id")
        if not isinstance(entity_id, str) or not entity_id:
            raise CWValidationError("CW entity id missing")
        if entity_id in identities:
            raise CWValidationError(f"duplicate canonical identity: {entity_id}")
        identities.add(entity_id)
        properties = entity.get("properties")
        if not isinstance(properties, list):
            raise CWValidationError(f"CW entity {entity_id} properties must be an array")
        for prop in properties:
            if not isinstance(prop, dict):
                raise CWValidationError(f"CW entity {entity_id} contains non-object Property")
            prop_id = prop.get("id")
            if not isinstance(prop_id, str) or not prop_id:
                raise CWValidationError(f"CW entity {entity_id} Property id missing")
            if prop_id in identities:
                raise CWValidationError(f"duplicate canonical identity: {prop_id}")
            identities.add(prop_id)
    return document


def ingest_cw(path: str | Path) -> dict[str, Any]:
    return validate_cw(load_cw(path))


def file_refs(document: dict[str, Any]) -> list[str]:
    validate_cw(document)
    return sorted([entity["id"] for entity in document.get("entities", []) if isinstance(entity, dict) and isinstance(entity.get("id"), str) and entity["id"].startswith("#FILE:")], key=str.lower)


def filetree(document: dict[str, Any]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for ref in file_refs(document):
        try:
            path = canonical_file_key_from_ref(ref)
        except Exception as exc:
            raise CWValidationError(f"invalid #FILE identity path: {ref}") from exc
        pure = PurePosixPath(path)
        cursor = root
        for part in pure.parts[:-1]:
            cursor = cursor.setdefault(part, {})
            if not isinstance(cursor, dict):
                raise CWValidationError(f"#FILE hierarchy collision at {part}")
        leaf = pure.parts[-1]
        if leaf in cursor:
            raise CWValidationError(f"#FILE hierarchy collision at {path}")
        cursor[leaf] = ref
    return root


def _tree_lines(tree: dict[str, Any], prefix: str = "") -> list[str]:
    items = sorted(tree.items(), key=lambda item: item[0].lower())
    lines: list[str] = []
    for index, (name, value) in enumerate(items):
        last = index == len(items) - 1
        branch = "└── " if last else "├── "
        lines.append(prefix + branch + name)
        if isinstance(value, dict):
            extension = "    " if last else "│   "
            lines.extend(_tree_lines(value, prefix + extension))
    return lines


def format_filetree(document: dict[str, Any]) -> str:
    lines = ["#FILE"]
    lines.extend(_tree_lines(filetree(document)))
    return "\n".join(lines)


def links(document: dict[str, Any]) -> list[dict[str, Any]]:
    validate_cw(document)
    result: list[dict[str, Any]] = []
    for entity in document.get("entities", []):
        if not isinstance(entity, dict):
            continue
        for prop in entity.get("properties", []):
            if not isinstance(prop, dict) or prop.get("property_type_ref") != "link":
                continue
            value = prop.get("value") if isinstance(prop.get("value"), dict) else {}
            result.append({"id": prop.get("id"), "owner_ref": entity.get("id"), "ruleset_ref": prop.get("ruleset_ref"), "link_type_ref": value.get("link_type_ref"), "parent_ref": value.get("parent_ref"), "child_ref": value.get("child_ref"), "properties": value.get("properties", {}) if isinstance(value.get("properties", {}), dict) else {}})
    return sorted(result, key=lambda item: str(item.get("id", "")).lower())


def format_links(document: dict[str, Any]) -> str:
    blocks: list[str] = []
    for item in links(document):
        blocks.append("\n".join([f"LINK {item['id']}", f"  type: {item['link_type_ref']}", f"  parent: {item['parent_ref']}", f"  child: {item['child_ref']}", f"  ruleset: {item['ruleset_ref']}"]))
    return "\n\n".join(blocks)
