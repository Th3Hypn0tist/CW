#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "Examples" / "Ultralight_CMS" / "Format" / "DR.json"


def dedupe(items: list[Any]) -> list[Any]:
    out = []
    seen = set()
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else repr(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


dr = json.loads(PATH.read_text(encoding="utf-8"))
if isinstance(dr.get("principles"), list):
    dr["principles"] = dedupe(dr["principles"])
for ruleset in dr.get("property_rulesets", []):
    if isinstance(ruleset, dict) and isinstance(ruleset.get("constraints"), list):
        ruleset["constraints"] = dedupe(ruleset["constraints"])
for ruleset in dr.get("link_rulesets", []):
    if isinstance(ruleset, dict):
        for field in ("constraints", "required_fields", "optional_fields"):
            if isinstance(ruleset.get(field), list):
                ruleset[field] = dedupe(ruleset[field])

dynamic = dr.get("event_execution_model", {}).get("dynamic_dispatch")
if isinstance(dynamic, dict):
    dynamic["failure_rule"] = (
        "A non-READY selector, malformed Property-address selector value, unresolved addressed Event, non-Event target, "
        "missing/ambiguous domain members surface or out-of-domain Event produces explicit INVALID dispatch. "
        "No fallback target, bare global Event-id lookup or silent no-op is permitted."
    )

PATH.write_text(json.dumps(dr, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("golden DR owner-local cleanup applied")
