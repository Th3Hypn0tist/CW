from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from CIC.identity import canonical_file_ref, observed_file_ref


class ReferenceResolutionError(ValueError):
    pass


def _file_ref(path: str) -> str:
    return observed_file_ref(path)


def _module_candidates(base: PurePosixPath) -> tuple[str, str]:
    text = str(base)
    return (f"{text}.py", f"{text}/__init__.py")


def _python_import_base(source_path: str, record: dict[str, Any]) -> PurePosixPath | None:
    kind = record.get("kind")
    if kind == "import":
        module = record.get("module")
        if not isinstance(module, str) or not module:
            return None
        return PurePosixPath(*module.split("."))

    if kind != "from_import":
        return None

    module = record.get("module") or ""
    if not isinstance(module, str):
        return None
    level = record.get("level", 0)
    if not isinstance(level, int) or level < 0:
        return None

    module_parts = [part for part in module.split(".") if part]
    if level == 0:
        if not module_parts:
            return None
        return PurePosixPath(*module_parts)

    base = PurePosixPath(source_path).parent
    for _ in range(level - 1):
        if str(base) in {"", "."}:
            return None
        base = base.parent
    return base.joinpath(*module_parts) if module_parts else base


_JS_TS_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")


def _lexical_relative_path(source_path: str, reference: str) -> PurePosixPath | None:
    if not (reference.startswith("./") or reference.startswith("../")):
        return None
    parts = list(PurePosixPath(source_path).parent.parts)
    for part in reference.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        return None
    return PurePosixPath(*parts)


def _js_ts_candidates(source_path: str, record: dict[str, Any]) -> tuple[tuple[str, ...], str | None]:
    reference = record.get("module")
    if not isinstance(reference, str) or not reference:
        return (), None
    base = _lexical_relative_path(source_path, reference)
    if base is None:
        return (), "EXTERNAL_OR_UNPROVEN_REFERENCE"

    if base.suffix:
        return (str(base),), None

    text = str(base)
    candidates: list[str] = []
    for suffix in _JS_TS_SUFFIXES:
        candidates.append(f"{text}{suffix}")
    for suffix in _JS_TS_SUFFIXES:
        candidates.append(f"{text}/index{suffix}")
    return tuple(candidates), None


def resolve_code_references(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve exact local implementation references while preserving both identity layers.

    Observed FILE refs preserve source-format paths for implementation evidence.
    Canonical endpoint refs are language-agnostic #FILE identities. Neither form
    grants canonical dependency semantics; dependency promotion stays separate.
    """
    if not isinstance(ir, dict) or not isinstance(ir.get("files"), list):
        raise ReferenceResolutionError("CIC Code IR requires files array")

    available: set[str] = set()
    for item in ir["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ReferenceResolutionError("CIC Code IR file requires path")
        available.add(item["path"])

    evidence: list[dict[str, Any]] = []
    for file_record in ir["files"]:
        source_path = file_record["path"]
        language_ir = file_record.get("language_ir")
        if not isinstance(language_ir, dict):
            continue
        language_id = language_ir.get("language_id")
        imports = language_ir.get("imports", [])
        if not isinstance(imports, list):
            raise ReferenceResolutionError(f"imports must be an array: {source_path}")

        for index, record in enumerate(imports):
            if not isinstance(record, dict):
                raise ReferenceResolutionError(f"import evidence must be an object: {source_path}")
            span = record.get("span") if isinstance(record.get("span"), dict) else {}
            target_reference = record.get("module")
            if not isinstance(target_reference, str) or not target_reference:
                if record.get("kind") == "from_import" and record.get("level"):
                    target_reference = "." * int(record.get("level", 0))
                else:
                    target_reference = repr(record)

            candidates: tuple[str, ...] = ()
            forced_unresolved_reason: str | None = None
            resolved_reason = "EXACT_LOCAL_MODULE"
            ambiguous_reason = "AMBIGUOUS_LOCAL_TARGET"

            if language_id == "python":
                base = _python_import_base(source_path, record)
                if base is not None and str(base) not in {"", "."}:
                    candidates = _module_candidates(base)
            elif language_id in {"javascript", "typescript"}:
                candidates, forced_unresolved_reason = _js_ts_candidates(source_path, record)
                resolved_reason = "EXACT_LOCAL_RELATIVE_MODULE"
                ambiguous_reason = "AMBIGUOUS_LOCAL_RELATIVE_MODULE"

            matches = tuple(candidate for candidate in candidates if candidate in available)
            if forced_unresolved_reason is not None:
                resolution_status = "UNRESOLVED"
                resolution_reason = forced_unresolved_reason
                target_path = None
            elif len(matches) == 1:
                resolution_status = "RESOLVED"
                resolution_reason = resolved_reason
                target_path = matches[0]
            elif len(matches) > 1:
                resolution_status = "UNRESOLVED"
                resolution_reason = ambiguous_reason
                target_path = None
            else:
                resolution_status = "UNRESOLVED"
                resolution_reason = "NO_PROVEN_LOCAL_TARGET"
                target_path = None

            evidence.append({
                "evidence_id": f"IMPORT::{source_path}::{index}",
                "source_entity_ref": _file_ref(source_path),
                "target_entity_ref": _file_ref(target_path) if target_path else None,
                "source_canonical_entity_ref": canonical_file_ref(source_path),
                "target_canonical_entity_ref": canonical_file_ref(target_path) if target_path else None,
                "target_reference": target_reference,
                "resolution_status": resolution_status,
                "resolution_reason": resolution_reason,
                "candidate_paths": list(candidates),
                "matched_paths": list(matches),
                "import_kind": record.get("kind"),
                "line": span.get("line"),
                "provenance": source_path,
                "evidence_kind": "implementation_import",
                "observed_identity_preserves_source_suffix": True,
                "canonical_identity_is_language_agnostic": True,
                "canonical_dependency_status": "UNRESOLVED",
                "canonical_semantic_authority": False,
                "cic_ir": dict(record),
            })

    return evidence
