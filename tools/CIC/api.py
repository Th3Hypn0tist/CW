from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import api_core as _core
from .api_core import ImportBundle, ImportResult
from .cw import ingest_cw
from .cw_version import finalize_cw_for_write, has_entity_version, next_version_timestamp, same_entity_payload, serialize_entity, verify_cw_versions
from .package_pipeline import materialize_package
from .profiles import profile_options


class ToolchainValidationError(ValueError):
    pass


DEFAULT_EXCLUDED_DIRS = _core.DEFAULT_EXCLUDED_DIRS
import_files = _core.import_files
_normalize_relative = _core._normalize_relative
_read_text = _core._read_text
_walk_source_files = _core._walk_source_files


def _is_cw_root(path: Path) -> bool:
    return (
        (path / "linter" / "cw_package_validate.py").is_file()
        and (path / "Examples" / "Ultralight_CMS" / "Format" / "CW.json").is_file()
        and (path / "Examples" / "Ultralight_CMS" / "Model" / "model.cw").is_file()
    )


def resolve_cw_root(value: str | Path | None = None) -> Path:
    if value is not None:
        root = Path(value).expanduser().resolve()
        if not _is_cw_root(root):
            raise ToolchainValidationError(f"CW root does not contain current package toolchain: {root}")
        return root
    if os.environ.get("CW_ROOT"):
        root = Path(os.environ["CW_ROOT"]).expanduser().resolve()
        if not _is_cw_root(root):
            raise ToolchainValidationError(f"CW_ROOT does not contain current package toolchain: {root}")
        return root
    for parent in Path(__file__).resolve().parents:
        if _is_cw_root(parent):
            return parent
    raise ToolchainValidationError("CW toolchain root not found; provide cw_root or CW_ROOT")


def _default_format_template(root: Path) -> Path:
    return root / "Examples" / "Ultralight_CMS" / "Format"


def _resolve_format_template(root: Path, value: str | Path | None) -> Path:
    template = Path(value).expanduser().resolve() if value is not None else _default_format_template(root)
    if not template.is_dir() or not (template / "CW.json").is_file() or not (template / "DR.json").is_file():
        raise ToolchainValidationError(f"CW Format template not found: {template}")
    return template


def _run(root: Path, script: str, args: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(root / "linter" / script), *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _semantic_validate(package_root: Path, *, cw_root: Path) -> dict[str, Any]:
    code, stdout, stderr = _run(cw_root, "cw_package_validate.py", [str(package_root), "--json"])
    if code != 0:
        raise ToolchainValidationError("generated CW package failed validation:\n" + (stderr or stdout))
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ToolchainValidationError(f"CW package validator returned invalid JSON: {exc}") from exc
    if report.get("result") != "READY":
        raise ToolchainValidationError(f"generated CW package did not validate READY: {report.get('result')!r}")
    return report


def validate_toolchain(
    *,
    cw_root: str | Path | None = None,
    spec_set: str | Path | None = None,
    format_template: str | Path | None = None,
) -> dict[str, Any]:
    del spec_set
    root = resolve_cw_root(cw_root)
    template = _resolve_format_template(root, format_template)
    cic_root = Path(__file__).resolve().parent
    compile_targets = [
        *sorted(cic_root.glob("*.py")),
        *sorted((cic_root / "modules").glob("*.py")),
        root / "linter" / "cw_package_validate.py",
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "py_compile", *(str(path) for path in compile_targets)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ToolchainValidationError("CW/CIC tool compile validation failed:\n" + (completed.stderr or completed.stdout))
    golden = template.parent
    report = _semantic_validate(golden, cw_root=root)
    return {
        "result": "READY",
        "authority": "package_local_format",
        "format_template": str(template),
        "golden": str(golden),
        "golden_report": report,
    }


def _model_root(package_root: Path) -> Path:
    candidate = package_root / "Model"
    return candidate if (candidate / "model.cw").is_file() else package_root


def _model_manifest(package_root: Path) -> Path:
    return _model_root(package_root) / "model.cw"


def _ingest_package(package_root: Path) -> dict[str, Any]:
    return ingest_cw(_model_root(package_root))


def _entities_by_id(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        e["id"]: e
        for e in document.get("entities", [])
        if isinstance(e, dict) and isinstance(e.get("id"), str)
    }


def _write_finalized_shards(package_root: Path, finalized: dict[str, Any]) -> None:
    entities = _entities_by_id(finalized)
    manifest_path = _model_manifest(package_root)
    manifest_root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in manifest.get("shards", []):
        if not isinstance(record, dict):
            continue
        entity = entities.get(record.get("entity_ref"))
        artifact = record.get("artifact_ref")
        if entity is None or not isinstance(artifact, str):
            raise ToolchainValidationError(f"CW version finalization cannot resolve shard: {record!r}")
        (manifest_root / Path(artifact)).write_text(serialize_entity(entity), encoding="utf-8")
    verify_cw_versions(_ingest_package(package_root))


def _asset_ref(entity: dict[str, Any]) -> str | None:
    refs = []
    for prop in entity.get("properties", []) if isinstance(entity.get("properties"), list) else []:
        if not isinstance(prop, dict) or prop.get("property_type_ref") != "asset":
            continue
        value = prop.get("value") if isinstance(prop.get("value"), dict) else {}
        ref = value.get("asset_ref")
        if isinstance(ref, str):
            refs.append(ref)
    if len(refs) > 1:
        raise ToolchainValidationError(f"Entity has multiple Asset refs: {entity.get('id')}")
    return refs[0] if refs else None


def _same_asset_bytes(old: dict[str, Any], new: dict[str, Any], old_root: Path, new_root: Path) -> bool:
    old_ref = _asset_ref(old)
    new_ref = _asset_ref(new)
    if old_ref != new_ref:
        return False
    if old_ref is None:
        return True
    old_path = old_root / Path(old_ref)
    new_path = new_root / Path(new_ref)
    return old_path.is_file() and new_path.is_file() and old_path.read_bytes() == new_path.read_bytes()


def _finalize_created(package_root: Path) -> None:
    _write_finalized_shards(package_root, finalize_cw_for_write(_ingest_package(package_root)))


def _finalize_updated(package_root: Path, previous_root: Path, previous: dict[str, Any]) -> None:
    verify_cw_versions(previous)
    candidate = _ingest_package(package_root)
    prior = _entities_by_id(previous)
    reconciled = copy.deepcopy(candidate)
    changed: set[str] = set()
    previous_changed_timestamps: list[str] = []
    for index, entity in enumerate(reconciled.get("entities", [])):
        if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
            continue
        old = prior.get(entity["id"])
        unchanged = (
            old is not None
            and has_entity_version(old)
            and same_entity_payload(old, entity)
            and _same_asset_bytes(old, entity, previous_root, package_root)
        )
        if unchanged:
            reconciled["entities"][index] = copy.deepcopy(old)
        else:
            changed.add(entity["id"])
            if old is not None and isinstance(old.get("timestamp"), str):
                previous_changed_timestamps.append(old["timestamp"])
    version_time = next_version_timestamp(previous_changed_timestamps) if changed else None
    _write_finalized_shards(
        package_root,
        finalize_cw_for_write(reconciled, changed_entity_refs=changed, timestamp=version_time),
    )


def _transaction_paths(target: Path) -> tuple[Path, Path]:
    token = uuid.uuid4().hex
    return (
        target.with_name(f".{target.name}.cic-new-{token}"),
        target.with_name(f".{target.name}.cic-old-{token}"),
    )


def _retarget(result: ImportResult, target: Path) -> ImportResult:
    return replace(
        result,
        cw_folder=target,
        cw_path=target / result.cw_path.relative_to(result.cw_folder),
        ir_path=target / result.ir_path.relative_to(result.cw_folder),
    )


def import_folder(
    code_folder: str | Path,
    cw_folder: str | Path,
    *,
    force: bool = False,
    cw_root: str | Path | None = None,
    spec_set: str | Path | None = None,
    format_template: str | Path | None = None,
    profile: str | None = None,
    validate_tools: bool = True,
    **kwargs: Any,
) -> ImportResult:
    source = Path(code_folder).expanduser().resolve()
    target = Path(cw_folder).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"code folder not found: {source}")
    if source == target:
        raise ValueError("CW output folder must differ from code folder")
    if target in source.parents:
        raise ValueError(f"CW output folder cannot contain the code folder: {target}")
    if source in target.parents:
        raise ValueError(f"CW output folder cannot be inside the code folder: {target}")
    if target.exists() and not target.is_dir():
        raise ValueError(f"CW output path exists and is not a directory: {target}")
    if target.exists() and not force:
        raise ValueError(f"CW output folder already exists: {target}; use --force to update it")

    profile_kwargs = profile_options(profile)
    for key, value in profile_kwargs.items():
        if key in kwargs:
            raise ValueError(f"CIC profile {profile!r} and explicit {key} cannot both be supplied")
        kwargs[key] = value

    root = resolve_cw_root(cw_root)
    template = _resolve_format_template(root, format_template)
    if validate_tools:
        validate_toolchain(cw_root=root, spec_set=spec_set, format_template=template)

    staged, backup = _transaction_paths(target)
    previous = None
    if target.exists():
        previous = _ingest_package(target)
        verify_cw_versions(previous)

    result = None
    try:
        result = _core.import_folder(source, staged, force=False, **kwargs)
        cw_path, ir_path, shard_count = materialize_package(staged, source, template)
        result = replace(result, cw_path=cw_path, ir_path=ir_path, shard_count=shard_count)
        _semantic_validate(staged, cw_root=root)
        if previous is None:
            _finalize_created(staged)
        else:
            _finalize_updated(staged, target, previous)
        verify_cw_versions(_ingest_package(staged))
        _semantic_validate(staged, cw_root=root)
        if previous is None:
            staged.rename(target)
        else:
            target.rename(backup)
            try:
                staged.rename(target)
            except Exception:
                backup.rename(target)
                raise
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise

    if result is None:
        raise RuntimeError("CIC import completed without ImportResult")
    return _retarget(result, target)
