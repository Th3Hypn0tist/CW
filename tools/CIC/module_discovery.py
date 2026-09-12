from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable


class ModuleDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class ModuleDiscoveryRule:
    rule_id: str
    language_id: str
    registry_path: str
    role: str
    package_binding_names: tuple[str, ...]
    skip_binding_name: str | None = None


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModuleDiscoveryError(f"{label} must be a non-empty string")
    return value


def _rule(record: ModuleDiscoveryRule | dict[str, Any]) -> ModuleDiscoveryRule:
    if isinstance(record, ModuleDiscoveryRule):
        return record
    if not isinstance(record, dict):
        raise ModuleDiscoveryError("module discovery rule must be an object")
    bindings = record.get("package_binding_names")
    if not isinstance(bindings, list) or not bindings or not all(isinstance(item, str) and item for item in bindings):
        raise ModuleDiscoveryError("package_binding_names must be a non-empty string array")
    skip = record.get("skip_binding_name")
    if skip is not None and (not isinstance(skip, str) or not skip):
        raise ModuleDiscoveryError("skip_binding_name must be a non-empty string when present")
    return ModuleDiscoveryRule(
        rule_id=_text(record.get("rule_id"), "rule_id"),
        language_id=_text(record.get("language_id"), "language_id"),
        registry_path=_text(record.get("registry_path"), "registry_path"),
        role=_text(record.get("role"), "role"),
        package_binding_names=tuple(bindings),
        skip_binding_name=skip,
    )


def _module_literals(language_ir: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    symbols = language_ir.get("symbols")
    if not isinstance(symbols, list):
        return result
    for symbol in symbols:
        if not isinstance(symbol, dict) or symbol.get("kind") != "variable" or "literal_value" not in symbol:
            continue
        names = symbol.get("names")
        if not isinstance(names, list) or len(names) != 1 or not isinstance(names[0], str) or not names[0]:
            continue
        result[names[0]] = symbol["literal_value"]
    return result


def _package_path(package_name: str) -> str:
    return package_name.replace(".", "/")


def _module_name(path: str, package_name: str) -> str | None:
    package_path = _package_path(package_name)
    prefix = package_path + "/"
    if not path.startswith(prefix) or not path.endswith(".py"):
        return None
    relative = path[len(prefix):-3]
    if not relative or "/" in relative:
        return None
    return relative


def detect_module_candidates(
    ir: dict[str, Any],
    rules: Iterable[ModuleDiscoveryRule | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Discover module roles only from explicit registry bindings and package membership.

    The result is implementation evidence. It does not create NodeType families,
    Entities, members, or any other canonical semantic claim.
    """
    if not isinstance(ir, dict):
        raise ModuleDiscoveryError("Code IR must be an object")
    normalized = tuple(_rule(item) for item in rules)
    ids = [item.rule_id for item in normalized]
    if len(ids) != len(set(ids)):
        raise ModuleDiscoveryError("duplicate module discovery rule_id")

    files = ir.get("files")
    if not isinstance(files, list):
        raise ModuleDiscoveryError("Code IR files must be an array")
    by_path = {
        item.get("path"): item
        for item in files
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rule in normalized:
        registry = by_path.get(rule.registry_path)
        if not isinstance(registry, dict):
            continue
        language_ir = registry.get("language_ir")
        if not isinstance(language_ir, dict) or language_ir.get("language_id") != rule.language_id:
            continue
        literals = _module_literals(language_ir)

        packages: list[str] = []
        for binding_name in rule.package_binding_names:
            value = literals.get(binding_name)
            if not isinstance(value, str) or not value:
                raise ModuleDiscoveryError(
                    f"{rule.rule_id} registry binding {binding_name!r} is missing or not a literal package string"
                )
            packages.append(value)

        skipped: set[str] = set()
        if rule.skip_binding_name is not None:
            raw_skip = literals.get(rule.skip_binding_name)
            if not isinstance(raw_skip, list) or not all(isinstance(item, str) for item in raw_skip):
                raise ModuleDiscoveryError(
                    f"{rule.rule_id} skip binding {rule.skip_binding_name!r} is missing or not a literal string collection"
                )
            skipped = set(raw_skip)

        for package_name in packages:
            for path, file_record in by_path.items():
                if not isinstance(path, str) or not isinstance(file_record, dict):
                    continue
                module_name = _module_name(path, package_name)
                if module_name is None or module_name in skipped:
                    continue
                key = (rule.rule_id, path)
                if key in seen:
                    continue
                seen.add(key)
                canonical_ref = file_record.get("canonical_file_ref")
                if not isinstance(canonical_ref, str) or not canonical_ref.startswith("#FILE:"):
                    continue
                candidates.append({
                    "candidate_id": f"MODULE_CANDIDATE::{rule.rule_id}::{canonical_ref}",
                    "role": rule.role,
                    "module_name": module_name,
                    "package_name": package_name,
                    "source_path": path,
                    "canonical_file_ref": canonical_ref,
                    "registry_path": rule.registry_path,
                    "discovery_rule_ref": rule.rule_id,
                    "authority": "implementation_evidence",
                    "canonical_ready": False,
                    "canonical_semantic_authority": False,
                })

    return sorted(candidates, key=lambda item: item["candidate_id"])
