from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from CIC import import_folder, import_files
from CIC.profiles import profile_options
from CIC.record_contracts import detect_record_contract_candidates


TYPES_SOURCE = '''from dataclasses import dataclass
from typing import Any

@dataclass
class TriggerDef:
    kind: str
    expr: str = ""
    pulse_ms: int = 0
    def to_dict(self) -> dict[str, Any]:
        return {"kind": str(self.kind), "expr": str(self.expr or ""), "pulse_ms": int(self.pulse_ms or 0)}

@dataclass
class TriggerState:
    state: str = "0"
    pulse_ms: int = 0
    def to_dict(self) -> dict[str, Any]:
        return {"state": "1" if str(self.state) == "1" else "0", "pulse_ms": int(self.pulse_ms or 0)}

@dataclass
class EventDef:
    trigger_name: str
    command: str
    def to_dict(self) -> dict[str, Any]:
        return {"trigger": str(self.trigger_name or ""), "command": str(self.command or "")}
'''


class CICRecordContractTests(unittest.TestCase):
    def test_serializer_shapes_preserve_observed_field_types(self) -> None:
        bundle = import_files([
            {"path": "system/lib/trigger/types.py", "content": TYPES_SOURCE},
        ])
        rules = profile_options("aigmos")["record_contract_rules"]
        candidates = detect_record_contract_candidates(bundle.ir, rules)
        self.assertEqual(len(candidates), 3)
        by_class = {item["source_class"]: item for item in candidates}

        trigger = {field["name"]: field["observed_type"] for field in by_class["TriggerDef"]["serialized_fields"]}
        self.assertEqual(trigger, {"kind": "string", "expr": "string", "pulse_ms": "integer"})

        state = {field["name"]: field["observed_type"] for field in by_class["TriggerState"]["serialized_fields"]}
        self.assertEqual(state, {"state": "string", "pulse_ms": "integer"})

        event = {field["name"]: field["observed_type"] for field in by_class["EventDef"]["serialized_fields"]}
        self.assertEqual(event, {"trigger": "string", "command": "string"})
        self.assertFalse(by_class["EventDef"]["canonical_ready"])

    def test_profile_import_persists_record_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "package"
            path = source / "system" / "lib" / "trigger" / "types.py"
            path.parent.mkdir(parents=True)
            path.write_text(TYPES_SOURCE, encoding="utf-8")
            import_folder(source, target, profile="aigmos")
            ir = json.loads((target / "Diagnostics" / "import.ir.json").read_text(encoding="utf-8"))
            candidates = ir["record_contract_candidates"]
            self.assertEqual({item["source_class"] for item in candidates}, {"TriggerDef", "TriggerState", "EventDef"})


if __name__ == "__main__":
    unittest.main()
