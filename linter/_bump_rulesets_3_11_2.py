#!/usr/bin/env python3
"""One-shot migration: CW Rulesets 3.11.1 -> 3.11.2.

This script exists only to generate the corrected locked artifact without
hand-rewriting the 120k+ source file. The workflow that invokes it removes this
script after generation.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "CanonicalWireframe_Dependency_Rules_v3.11.1.json"
TARGET = ROOT / "CanonicalWireframe_Dependency_Rules_v3.11.2.json"
HISTORY = ROOT / "History" / SOURCE.name


def replace_principle(principles: list[str], old: str, new: str) -> None:
    try:
        index = principles.index(old)
    except ValueError as exc:
        raise SystemExit(f"expected v3.11.1 principle not found: {old}") from exc
    principles[index] = new


def main() -> None:
    if TARGET.exists():
        print(f"{TARGET.name} already exists; nothing to do")
        return

    original_text = SOURCE.read_text(encoding="utf-8")
    data = json.loads(original_text)

    if data.get("id") != "CW_RULESETS" or data.get("version") != "3.11.1":
        raise SystemExit("source is not CW_RULESETS v3.11.1")

    function_rules = [
        rule for rule in data.get("property_rulesets", [])
        if rule.get("property_type_ref") == "function"
    ]
    if len(function_rules) != 1:
        raise SystemExit(f"expected exactly one Function Ruleset, got {len(function_rules)}")

    function_rule = function_rules[0]
    logic_schema = function_rule.get("logic_schema")
    if not isinstance(logic_schema, dict):
        raise SystemExit("RULESET_FUNCTION.logic_schema missing")

    shared = data.get("shared_value_types")
    if not isinstance(shared, dict) or not isinstance(shared.get("function_logic"), dict):
        raise SystemExit("shared_value_types.function_logic missing")

    # The bug: this shared schema still described the pre-primitive
    # representation_ref/source form. Make it mirror the structured canonical
    # Function.logic schema exactly for the machine-significant shape.
    shared_logic = shared["function_logic"]
    for field in ("required", "optional", "fields"):
        shared_logic[field] = copy.deepcopy(logic_schema[field])

    shared_logic["meaning"] = (
        "Structured language-independent normalized Function behavior. "
        "primitive_set_ref selects the canonical Logic Primitive Set; body is the ordered semantic authority; "
        "representations are optional non-authoritative projections."
    )
    shared_logic["rules"] = [
        "primitive_set_ref resolves exactly one Logic Primitive Set inside the pinned immutable specification closure.",
        "body contains ordered structured logic statements governed recursively by the resolved Logic Primitive Set.",
        "representations, when present, contain representation_ref + source projections for human/tool-facing notation such as python, javascript, sql or hgi.",
        "representations are not canonical behavior authority and MUST NOT be parsed to invent missing canonical semantics.",
        "logic does not replace canonical input_refs, output_refs, function_call Links, Event/Effect causality or other explicit canonical semantics.",
        "Presence of logic does not by itself prove correspondence with an external implementation or runtime execution."
    ]

    principles = data.get("principles")
    if not isinstance(principles, list):
        raise SystemExit("principles missing")

    replace_principle(
        principles,
        "Function logic MAY carry an explicit normalized operational representation through logic.representation_ref + logic.source.",
        "Function logic MAY carry explicit structured normalized operational behavior through logic.primitive_set_ref + logic.body; optional logic.representations[] items are non-authoritative projections."
    )
    replace_principle(
        principles,
        "Function input/output semantics remain explicit through RULESET_FUNCTION input_refs/output_refs and function-to-function use remains explicit through function_call Links; consumers MUST NOT invent canonical I/O or call edges by parsing logic.source.",
        "Function input/output semantics remain explicit through RULESET_FUNCTION input_refs/output_refs and function-to-function use remains explicit through function_call Links; consumers MUST NOT invent canonical I/O or call edges by parsing logic.representations[].source."
    )
    replace_principle(
        principles,
        "Function logic representation vocabulary is open; representation_ref identifies the notation/language used by logic.source, including values such as python, javascript, sql or hgi.",
        "Function logic representation vocabulary is open; each optional logic.representations[] representation_ref identifies the notation/language used by that representation source, including values such as python, javascript, sql or hgi."
    )

    data["version"] = "3.11.2"

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(original_text, encoding="utf-8")
    TARGET.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SOURCE.unlink()

    print(f"archived: {HISTORY.relative_to(ROOT)}")
    print(f"created:  {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
