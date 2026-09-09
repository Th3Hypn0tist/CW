from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol


class Extractor(Protocol):
    def __call__(self, path: str, source: str) -> dict: ...


@dataclass(frozen=True)
class LanguageModule:
    language_id: str
    suffixes: tuple[str, ...]
    extractor: Extractor | None = None

    @property
    def parser_available(self) -> bool:
        return self.extractor is not None


BUILTIN_LANGUAGE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "javascript": (".js", ".mjs", ".cjs", ".jsx"),
    "typescript": (".ts", ".tsx"),
    "html": (".html", ".htm"),
    "css": (".css",),
    "c_cpp": (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"),
    "csharp": (".cs",),
    "java": (".java",),
    "kotlin": (".kt", ".kts"),
    "go": (".go",),
    "rust": (".rs",),
    "php": (".php",),
    "hgi": (".hgi",),
}

_MODULES: list[LanguageModule] = []


def register(module: LanguageModule, *, replace: bool = False) -> None:
    global _MODULES
    if replace:
        _MODULES = [item for item in _MODULES if item.language_id != module.language_id]
    elif any(item.language_id == module.language_id for item in _MODULES):
        raise ValueError(f"language module already registered: {module.language_id}")
    _MODULES.append(module)


def modules() -> tuple[LanguageModule, ...]:
    return tuple(_MODULES)


def recognized_suffixes() -> frozenset[str]:
    return frozenset(suffix for suffixes in BUILTIN_LANGUAGE_SUFFIXES.values() for suffix in suffixes)


def is_recognized_source_path(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in recognized_suffixes()


def detect(path: str) -> LanguageModule | None:
    suffix = PurePosixPath(path).suffix.lower()
    matches = [module for module in _MODULES if suffix in module.suffixes]
    if len(matches) > 1:
        raise ValueError(f"ambiguous CIC language detection for {path}: {[item.language_id for item in matches]}")
    return matches[0] if matches else None


def _empty_language_ir(language_id: str, *, parser_id: str | None, diagnostic: dict) -> dict:
    return {"language_id": language_id, "parser_id": parser_id, "parser_available": False, "diagnostics": [diagnostic], "symbols": [], "imports": [], "exports": [], "evidence": []}


def _python_module_function_exports(symbols: object) -> list[dict]:
    if not isinstance(symbols, list):
        return []
    exports: list[dict] = []
    for symbol in symbols:
        if not isinstance(symbol, dict) or symbol.get("kind") != "function":
            continue
        name = symbol.get("name")
        qualified = symbol.get("qualified_name")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(qualified, str) or not qualified:
            qualified = name
        exports.append({"kind": "local_export", "exported_name": name, "local_name": name, "target_kind": "function", "target_qualified_name": qualified, "evidence_kind": "python_module_binding"})
    return exports


def extract(path: str, source: str) -> dict:
    module = detect(path)
    if module is None:
        return _empty_language_ir("unclassified", parser_id=None, diagnostic={"code": "LANGUAGE_UNCLASSIFIED", "message": "no registered language evidence matched this path"})
    if module.extractor is None:
        return _empty_language_ir(module.language_id, parser_id=module.language_id, diagnostic={"code": "PARSER_UNAVAILABLE", "message": f"no CIC extractor is registered for {module.language_id}"})
    result = module.extractor(path, source)
    if not isinstance(result, dict):
        raise TypeError(f"CIC module {module.language_id} returned non-dict IR")
    result.setdefault("language_id", module.language_id)
    result.setdefault("parser_id", module.language_id)
    result.setdefault("parser_available", True)
    result.setdefault("diagnostics", [])
    result.setdefault("symbols", [])
    result.setdefault("imports", [])
    if module.language_id == "python" and "exports" not in result:
        result["exports"] = _python_module_function_exports(result.get("symbols"))
    result.setdefault("exports", [])
    result.setdefault("evidence", [])
    return result


def install_builtin_modules(*, python_extractor: Extractor | None = None, javascript_extractor: Extractor | None = None, html_extractor: Extractor | None = None, css_extractor: Extractor | None = None) -> None:
    extractors = {"python": python_extractor, "javascript": javascript_extractor, "html": html_extractor, "css": css_extractor}
    existing = {module.language_id: module for module in _MODULES}
    for language_id, suffixes in BUILTIN_LANGUAGE_SUFFIXES.items():
        supplied = extractors.get(language_id)
        current = existing.get(language_id)
        if current is None:
            register(LanguageModule(language_id, suffixes, supplied))
            continue
        if supplied is not None and current.extractor is not supplied:
            register(LanguageModule(language_id, suffixes, supplied), replace=True)
