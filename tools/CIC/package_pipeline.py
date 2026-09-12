from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote


class CICPackageError(ValueError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CICPackageError(f"JSON root must be object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _id_fragment(value: str) -> str:
    return quote(value, safe="-._~")


def _asset_extension(source_path: str) -> str:
    return PurePosixPath(source_path).suffix.lower()


def _asset_file_type(dr: dict[str, Any], extension: str) -> str:
    records = dr.setdefault("asset_file_types", [])
    if not isinstance(records, list):
        raise CICPackageError("Format/DR.json asset_file_types must be an array")
    for record in records:
        if not isinstance(record, dict):
            continue
        extensions = record.get("extensions")
        if isinstance(extensions, list) and extension in extensions and isinstance(record.get("id"), str):
            return record["id"]
    stem = extension[1:] if extension.startswith(".") else extension
    clean = "".join(char.lower() if char.isalnum() else "_" for char in stem).strip("_") or "no_extension"
    file_type_ref = f"source_{clean}"
    existing_ids = {record.get("id") for record in records if isinstance(record, dict)}
    suffix = 2
    base = file_type_ref
    while file_type_ref in existing_ids:
        hit = next((record for record in records if isinstance(record, dict) and record.get("id") == file_type_ref), None)
        if isinstance(hit, dict) and hit.get("extensions") == [extension]:
            return file_type_ref
        file_type_ref = f"{base}_{suffix}"
        suffix += 1
    records.append({"id": file_type_ref, "extensions": [extension]})
    return file_type_ref


def _asset_ref(entity_ref: str, extension: str) -> str:
    encoded = quote(entity_ref, safe="-._~")
    return f"Assets/FILE/{encoded}{extension}"


def _asset_property(entity_ref: str, asset_ref: str, file_type_ref: str) -> dict[str, Any]:
    return {
        "id": f"ASSET::{entity_ref}",
        "property_type_ref": "asset",
        "ruleset_ref": "RULESET_ASSET",
        "status": "unlocked",
        "value": {
            "asset_ref": asset_ref,
            "file_type_ref": file_type_ref,
            "properties": {},
        },
    }


def _is_import_provenance_data(prop: dict[str, Any], entity_ref: str) -> bool:
    return prop.get("id") in {
        f"DATA::{entity_ref}::SOURCE_PATH",
        f"DATA::{entity_ref}::SOURCE_LANGUAGE",
    }


def _dependency_properties(ir: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for record in ir.get("reference_evidence", []) if isinstance(ir.get("reference_evidence"), list) else []:
        if not isinstance(record, dict) or record.get("resolution_status") != "RESOLVED":
            continue
        consumer = record.get("source_canonical_entity_ref")
        provider = record.get("target_canonical_entity_ref")
        evidence_id = record.get("evidence_id")
        if not isinstance(consumer, str) or not isinstance(provider, str) or consumer == provider:
            continue
        key = (consumer, provider)
        grouped.setdefault(key, [])
        if isinstance(evidence_id, str) and evidence_id not in grouped[key]:
            grouped[key].append(evidence_id)

    by_owner: dict[str, list[dict[str, Any]]] = {}
    for (consumer, provider), evidence_refs in sorted(grouped.items()):
        prop_id = f"LINK::DEPENDENCY::{_id_fragment(consumer)}::{_id_fragment(provider)}"
        by_owner.setdefault(consumer, []).append({
            "id": prop_id,
            "property_type_ref": "link",
            "ruleset_ref": "RULESET_LINK_DEPENDENCY",
            "status": "unlocked",
            "value": {
                "link_type_ref": "dependency",
                "parent_ref": provider,
                "child_ref": consumer,
                "properties": {"implementation_evidence_refs": sorted(evidence_refs)},
            },
        })
    return by_owner


def materialize_package(
    staging_root: str | Path,
    source_root: str | Path,
    format_template: str | Path,
) -> tuple[Path, Path, int]:
    """Transform CIC parser output into the current self-contained CW package.

    Input staging layout is the parser/evidence layout produced by api_core:
    model.cw, FILE/**/*.cw and import.ir.json. The result is Format/Model/Assets
    plus non-canonical Diagnostics/import.ir.json.
    """
    root = Path(staging_root).resolve()
    source = Path(source_root).resolve()
    template = Path(format_template).resolve()
    old_manifest = root / "model.cw"
    old_file_root = root / "FILE"
    old_ir = root / "import.ir.json"
    if not old_manifest.is_file() or not old_file_root.is_dir() or not old_ir.is_file():
        raise CICPackageError("CIC parser staging output is incomplete")
    if not template.is_dir() or not (template / "CW.json").is_file():
        raise CICPackageError(f"Format template is invalid: {template}")

    format_root = root / "Format"
    model_root = root / "Model"
    assets_root = root / "Assets" / "FILE"
    diagnostics_root = root / "Diagnostics"
    if any(path.exists() for path in (format_root, model_root, root / "Assets", diagnostics_root)):
        raise CICPackageError("CIC package target directories already exist in staging output")

    shutil.copytree(template, format_root)
    model_root.mkdir()
    shutil.move(str(old_file_root), str(model_root / "FILE"))
    shutil.move(str(old_manifest), str(model_root / "model.cw"))
    diagnostics_root.mkdir()
    shutil.move(str(old_ir), str(diagnostics_root / "import.ir.json"))
    assets_root.mkdir(parents=True)

    manifest_path = model_root / "model.cw"
    manifest = _read_json(manifest_path)
    ir = _read_json(diagnostics_root / "import.ir.json")
    dr_path = format_root / "DR.json"
    dr = _read_json(dr_path)
    dependencies = _dependency_properties(ir)

    files = [record for record in ir.get("files", []) if isinstance(record, dict)]
    by_entity = {
        record.get("canonical_file_ref"): record
        for record in files
        if isinstance(record.get("canonical_file_ref"), str)
    }

    shard_count = 0
    for record in manifest.get("shards", []) if isinstance(manifest.get("shards"), list) else []:
        if not isinstance(record, dict):
            continue
        entity_ref = record.get("entity_ref")
        artifact_ref = record.get("artifact_ref")
        file_record = by_entity.get(entity_ref)
        if not isinstance(entity_ref, str) or not isinstance(artifact_ref, str) or not isinstance(file_record, dict):
            raise CICPackageError(f"cannot bind parser shard to source asset: {record!r}")
        shard_path = model_root / PurePosixPath(artifact_ref)
        entity = _read_json(shard_path)
        source_path = file_record.get("path")
        if not isinstance(source_path, str):
            raise CICPackageError(f"source path missing for {entity_ref}")
        extension = _asset_extension(source_path)
        file_type_ref = _asset_file_type(dr, extension)
        asset_ref = _asset_ref(entity_ref, extension)
        source_asset = source / PurePosixPath(source_path)
        target_asset = root / PurePosixPath(asset_ref)
        if not source_asset.is_file():
            raise CICPackageError(f"source asset disappeared during import: {source_path}")
        target_asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_asset, target_asset)

        entity["entity_type_ref"] = "FILE"
        entity.pop("required_links", None)
        properties = [
            prop for prop in entity.get("properties", [])
            if isinstance(prop, dict) and not _is_import_provenance_data(prop, entity_ref)
        ]
        properties = [prop for prop in properties if prop.get("property_type_ref") != "asset"]
        entity["properties"] = [
            _asset_property(entity_ref, asset_ref, file_type_ref),
            *properties,
            *dependencies.get(entity_ref, []),
        ]
        _write_json(shard_path, entity)
        shard_count += 1

    manifest["format"] = {"contract_format": "CANONICAL_CONTRACT", "format_version": "2.4.3"}
    identity = manifest.setdefault("identity", {})
    identity.update({
        "id": "CIC_IMPORTED_CODE_MODEL",
        "name": "CIC Imported Code Model",
        "type": "system_architecture",
        "version": "0.4.0",
    })
    manifest["specification_ref"] = "LOCAL_FORMAT:Format"
    manifest["purpose"] = "Self-contained CW package projected deterministically from source code by CIC."
    manifest.pop("scope", None)
    manifest.setdefault("serialization", {}).update({
        "mode": "cw_entity_shards",
        "one_entity_one_shard": True,
        "manifest": "Model/model.cw",
        "source_suffix_in_shard_name": False,
    })
    invariants = manifest.setdefault("constraints", {}).setdefault("invariants", [])
    if isinstance(invariants, list):
        invariants[:] = [
            item for item in invariants
            if not (isinstance(item, dict) and item.get("id") == "CIC_IMPORT_IS_SPEC_UNBOUND")
        ]
        invariants.extend([
            {"id": "CIC_SELF_CONTAINED_PACKAGE", "rule": "The generated package carries its complete local Format closure under Format/."},
            {"id": "CIC_SOURCE_ASSET", "rule": "Every imported #FILE Entity owns its original source file as its one opaque Asset."},
            {"id": "CIC_DEPENDENCY_FROM_IMPORT", "rule": "Exactly resolved internal implementation imports project to dependency Links with provider parent_ref and consumer child_ref."},
        ])
    _write_json(manifest_path, manifest)
    _write_json(dr_path, dr)

    return manifest_path, diagnostics_root / "import.ir.json", shard_count
