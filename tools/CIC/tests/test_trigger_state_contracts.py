from __future__ import annotations

import unittest

from CIC import import_files
from CIC.profiles import profile_options
from CIC.state_contracts import detect_state_contract_candidates


STORE_SOURCE = '''TRIGGER_DEFS_ROOT = "#SYSTEM:runtime:triggers"
EVENT_DEFS_ROOT = "#SYSTEM:runtime:events"
TRIGGER_STATE_ROOT = "#SYSTEM:runtime:trigger_state"

def _trigger_def_symbol(name):
    return f"{TRIGGER_DEFS_ROOT}:{name}"

def _event_def_symbol(name):
    return f"{EVENT_DEFS_ROOT}:{name}"

def _trigger_runtime_symbol(name):
    return f"{TRIGGER_STATE_ROOT}:{name}"

def load_trigger_def(state, name):
    return read_value(state, _trigger_def_symbol(name), None)

def save_trigger_def(state, name, value):
    return write_value(state, _trigger_def_symbol(name), value)

def delete_trigger_def(state, name):
    return delete_value(state, _trigger_def_symbol(name))

def load_event_def(state, name):
    return read_value(state, _event_def_symbol(name), None)

def save_event_def(state, name, value):
    return write_value(state, _event_def_symbol(name), value)

def load_trigger_state(state, name):
    return read_value(state, _trigger_runtime_symbol(name), None)

def save_trigger_state(state, name, value):
    return write_value(state, _trigger_runtime_symbol(name), value)
'''


class CICTriggerStateContractTests(unittest.TestCase):
    def test_dynamic_symbol_builders_preserve_state_root_ownership(self) -> None:
        bundle = import_files([
            {"path": "system/lib/trigger/store.py", "content": STORE_SOURCE},
        ])
        rules = [
            item for item in profile_options("aigmos")["state_contract_rules"]
            if item["source_path"] == "system/lib/trigger/store.py"
        ]
        candidates = detect_state_contract_candidates(bundle.ir, rules)
        self.assertEqual(len(candidates), 3)
        by_symbol = {item["state_symbol"]: item for item in candidates}

        trigger_defs = by_symbol["#SYSTEM:runtime:triggers"]
        self.assertIn("_trigger_def_symbol", trigger_defs["root_resolvers"])
        self.assertEqual(trigger_defs["readers"], ["load_trigger_def"])
        self.assertEqual(trigger_defs["writers"], ["delete_trigger_def", "save_trigger_def"])

        event_defs = by_symbol["#SYSTEM:runtime:events"]
        self.assertEqual(event_defs["readers"], ["load_event_def"])
        self.assertEqual(event_defs["writers"], ["save_event_def"])

        trigger_state = by_symbol["#SYSTEM:runtime:trigger_state"]
        self.assertEqual(trigger_state["readers"], ["load_trigger_state"])
        self.assertEqual(trigger_state["writers"], ["save_trigger_state"])

        for item in candidates:
            self.assertEqual(item["source_entity_ref"], "#FILE:system:lib:trigger:store")
            self.assertFalse(item["canonical_ready"])
            self.assertFalse(item["canonical_semantic_authority"])


if __name__ == "__main__":
    unittest.main()
