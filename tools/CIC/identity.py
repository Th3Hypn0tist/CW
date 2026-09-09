from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


class CICIdentityError(ValueError):
    pass


CANONICAL_FILE_PREFIX = "#FILE:"
OBSERVED_FILE_PREFIX = "FILE::"


def normalize_source_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CICIdentityError("CIC source path must be a non-empty string")
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CICIdentityError(f"invalid CIC source path: {value!r}")
    if any(":" in part for part in path.parts):
        raise CICIdentityError(f"CIC source path contains ':' which cannot map losslessly to #FILE identity: {value!r}")
    return str(path)


def observed_file_ref(source_path: Any) -> str:
    return f"{OBSERVED_FILE_PREFIX}{normalize_source_path(source_path)}"


def canonical_file_key(source_path: Any) -> str:
    """Return the language-agnostic path key used by canonical CW.

    Only the final source-format suffix is removed. Directory structure and any
    earlier dots in the basename remain semantic path material.

    Examples:
      foo/bar.py    -> foo/bar
      web/app.js    -> web/app
      schema.v1.json -> schema.v1
      .gitignore    -> .gitignore
    """
    normalized = normalize_source_path(source_path)
    path = PurePosixPath(normalized)
    basename = path.name
    suffix = path.suffix
    stem = basename[:-len(suffix)] if suffix else basename
    if not stem or stem in {".", ".."}:
        raise CICIdentityError(f"source basename cannot produce canonical #FILE identity: {source_path!r}")
    parts = [*path.parts[:-1], stem]
    return "/".join(parts)


def canonical_file_ref(source_path: Any) -> str:
    key = canonical_file_key(source_path)
    return CANONICAL_FILE_PREFIX + ":".join(PurePosixPath(key).parts)


def canonical_file_ref_from_observed_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(OBSERVED_FILE_PREFIX):
        raise CICIdentityError(f"observed FILE ref required: {value!r}")
    return canonical_file_ref(value[len(OBSERVED_FILE_PREFIX):])


def canonical_file_key_from_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(CANONICAL_FILE_PREFIX):
        raise CICIdentityError(f"canonical #FILE ref required: {value!r}")
    raw = value[len(CANONICAL_FILE_PREFIX):]
    parts = raw.split(":") if raw else []
    if not parts or any(not part or part in {".", ".."} or "/" in part or "\\" in part for part in parts):
        raise CICIdentityError(f"invalid canonical #FILE ref: {value!r}")
    return "/".join(parts)


def canonical_file_shard_path(value: Any) -> str:
    """Return physical .cw shard path for a source path or canonical #FILE ref."""
    if isinstance(value, str) and value.startswith(CANONICAL_FILE_PREFIX):
        key = canonical_file_key_from_ref(value)
    else:
        key = canonical_file_key(value)
    path = PurePosixPath(key)
    return str(PurePosixPath("FILE", *path.parts[:-1], f"{path.name}.cw"))


def canonical_function_ref(source_path: Any, qualified_name: str) -> str:
    if not isinstance(qualified_name, str) or not qualified_name:
        raise CICIdentityError("Function qualified_name must be a non-empty string")
    return f"FUNCTION::{canonical_file_ref(source_path)}::{qualified_name}"


def assert_no_canonical_file_collisions(source_paths: list[str]) -> dict[str, str]:
    by_ref: dict[str, str] = {}
    for source_path in source_paths:
        ref = canonical_file_ref(source_path)
        previous = by_ref.get(ref)
        if previous is not None and previous != source_path:
            raise CICIdentityError(
                f"canonical #FILE identity collision: {previous!r} and {source_path!r} both map to {ref}"
            )
        by_ref[ref] = source_path
    return by_ref
