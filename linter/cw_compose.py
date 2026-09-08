from __future__ import annotations

import copy
from pathlib import Path, PurePosixPath
from typing import Any, Callable


class CWCompositionError(ValueError):
    pass


def _entity_shard(value: Any) -> bool:
    if not isinstance(value, dict) or isinstance(value.get("format"), dict):
        return False
    required = ("id", "name", "entity_type_ref", "status", "properties")
    return all(field in value for field in required)


def _normalize_artifact_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CWCompositionError("CW shard artifact_ref must be a non-empty string")
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CWCompositionError(f"invalid CW shard artifact_ref: {value!r}")
    if path.suffix not in {".cw", ".json"}:
        raise CWCompositionError(f"CW shard artifact_ref must use .cw or .json serialization: {value!r}")
    return str(path)


def compose_documents(
    paths: list[Path],
    read_document: Callable[[Path], dict[str, Any]],
) -> list[tuple[Path, dict[str, Any]]]:
    """Load full contract documents and compose explicitly sharded CW roots.

    A sharded root opts into composition by declaring a `shards` array. Every
    declared shard is a direct canonical Entity object. Paths locate serialized
    content only; identity and NodeType come from the Entity itself.
    """
    loaded: dict[Path, dict[str, Any]] = {}
    roots: list[tuple[Path, dict[str, Any]]] = []
    entity_shards: list[Path] = []
    for path in paths:
        document = read_document(path)
        if not isinstance(document, dict):
            raise CWCompositionError(f"{path}: CW/JSON serialization root must be an object")
        loaded[path.resolve()] = document
        if isinstance(document.get("format"), dict):
            roots.append((path, document))
        elif _entity_shard(document):
            entity_shards.append(path)

    if len(paths) == 1 and not roots:
        if entity_shards:
            raise CWCompositionError(f"{paths[0]}: standalone Node shard requires a composition root")
        raise CWCompositionError(f"{paths[0]}: no Canonical Contract root found")

    result: list[tuple[Path, dict[str, Any]]] = []
    for root_path, root in roots:
        shards = root.get("shards")
        if shards is None:
            result.append((root_path, root))
            continue
        if not isinstance(shards, list):
            raise CWCompositionError(f"{root_path}: shards must be an array")
        root_entities = root.get("entities")
        if not isinstance(root_entities, list):
            raise CWCompositionError(f"{root_path}: sharded root entities must be an array")
        if root_entities:
            raise CWCompositionError(f"{root_path}: sharded root must not duplicate inline Entity definitions")

        entities: list[dict[str, Any]] = []
        seen_entities: set[str] = set()
        seen_artifacts: set[str] = set()
        root_dir = root_path.parent.resolve()
        for index, record in enumerate(shards):
            if not isinstance(record, dict):
                raise CWCompositionError(f"{root_path}: shards[{index}] must be an object")
            entity_ref = record.get("entity_ref")
            if not isinstance(entity_ref, str) or not entity_ref:
                raise CWCompositionError(f"{root_path}: shards[{index}].entity_ref missing")
            artifact_ref = _normalize_artifact_ref(record.get("artifact_ref"))
            if artifact_ref in seen_artifacts:
                raise CWCompositionError(f"{root_path}: duplicate shard artifact_ref {artifact_ref!r}")
            seen_artifacts.add(artifact_ref)

            relative = PurePosixPath(artifact_ref)
            shard_path = (root_dir / Path(*relative.parts)).resolve()
            if shard_path != root_dir and root_dir not in shard_path.parents:
                raise CWCompositionError(f"{root_path}: shard escapes model directory: {artifact_ref}")
            shard = loaded.get(shard_path)
            if shard is None:
                raise CWCompositionError(f"{root_path}: declared shard not discovered: {artifact_ref}")
            if not _entity_shard(shard):
                raise CWCompositionError(f"{root_path}: shard must contain one direct canonical Entity: {artifact_ref}")
            if shard.get("id") != entity_ref:
                raise CWCompositionError(
                    f"{root_path}: shard identity mismatch for {artifact_ref}: "
                    f"manifest {entity_ref!r}, Entity {shard.get('id')!r}"
                )
            if entity_ref in seen_entities:
                raise CWCompositionError(f"{root_path}: duplicate canonical Entity id {entity_ref!r}")
            seen_entities.add(entity_ref)
            entities.append(copy.deepcopy(shard))

        composed = copy.deepcopy(root)
        composed["entities"] = entities
        result.append((root_path, composed))
    return result
