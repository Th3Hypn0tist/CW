from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


_UNCLASSIFIED_CODES = frozenset({"LANGUAGE_UNCLASSIFIED"})
_UNSUPPORTED_CODES = frozenset({"PARSER_UNAVAILABLE"})
_WARNING_CODES = frozenset({
    "UNMATCHED_END_TAG",
    "IMPLICITLY_CLOSED_TAG",
    "UNCLOSED_TAG",
})


def classify_diagnostic(diagnostic: dict[str, Any]) -> str:
    code = str(diagnostic.get("code") or "UNKNOWN")
    if code in _UNCLASSIFIED_CODES:
        return "unclassified"
    if code in _UNSUPPORTED_CODES:
        return "unsupported"
    if code in _WARNING_CODES:
        return "parser_warning"
    return "parser_error"


def summarize_diagnostics(files: Iterable[dict[str, Any]]) -> dict[str, Any]:
    by_category: Counter[str] = Counter()
    by_code: Counter[str] = Counter()
    by_language: dict[str, Counter[str]] = {}
    affected_files: dict[str, set[str]] = {
        "parser_error": set(),
        "parser_warning": set(),
        "unsupported": set(),
        "unclassified": set(),
    }

    total = 0
    for file_record in files:
        if not isinstance(file_record, dict):
            continue
        path = str(file_record.get("path") or "<unknown>")
        language_ir = file_record.get("language_ir")
        if not isinstance(language_ir, dict):
            continue
        language = str(language_ir.get("language_id") or "unclassified")
        for diagnostic in language_ir.get("diagnostics", []):
            if not isinstance(diagnostic, dict):
                continue
            total += 1
            code = str(diagnostic.get("code") or "UNKNOWN")
            category = classify_diagnostic(diagnostic)
            by_category[category] += 1
            by_code[code] += 1
            by_language.setdefault(language, Counter())[category] += 1
            affected_files.setdefault(category, set()).add(path)

    return {
        "total": total,
        "parser_errors": by_category["parser_error"],
        "parser_warnings": by_category["parser_warning"],
        "unsupported": by_category["unsupported"],
        "unclassified": by_category["unclassified"],
        "by_category": dict(sorted(by_category.items())),
        "by_code": dict(sorted(by_code.items())),
        "by_language": {
            language: dict(sorted(counter.items()))
            for language, counter in sorted(by_language.items())
        },
        "affected_files": {
            category: sorted(paths)
            for category, paths in sorted(affected_files.items())
            if paths
        },
    }
