from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from CIC import import_folder, import_files
from CIC.profiles import profile_options
from CIC.state_contracts import detect_state_contract_candidates


STORE_SOURCE = '''RUNNER_DEFS_SYMBOL = "#SYSTEM:runtime:runners"

def _state_get_value(state, symbol):
    return None

def _state_set_value(state, symbol, value):
    return None

def load_runner_defs(state):
    data = _state_get_value(state, RUNNER_DEFS_SYMBOL)
    return data

def save_runner_defs(state, payload):
    _state_set_value(state, RUNNER_DEFS_SYMBOL, payload)
'''


class CICStateContractTests(unittest.TestCase):
    def test_runner_state_symbol_reader_writer_are_source_backed(self) -> None:
        bundle = import_files([
            {"path": "system/runtime/runner_store.py", "content": STORE_SOURCE},
        ])
        rules = profile_options("aigmos")["state_contract_rules"]
        candidates = detect_state_contract_candidates(bundle.ir, rules)
        self.assertEqual(len(candidates), 1)
        item = candidates[0]
        self.assertEqual(item["state_symbol"], "#SYSTEM:runtime:runners")
        self.assertEqual(item["source_entity_ref"], "#FILE:system:runtime:runner_store")
        self.assertEqual(item["readers"], ["load_runner_defs"])
        self.assertEqual(item["writers"], ["save_runner_defs"])
        self.assertFalse(item["canonical_ready"])
        self.assertFalse(item["canonical_semantic_authority"])

    def test_aigmos_profile_persists_candidate_in_diagnostics_ir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "package"
            file_path = source / "system" / "runtime" / "runner_store.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(STORE_SOURCE, encoding="utf-8")
            import_folder(source, target, profile="aigmos")
            ir = json.loads((target / "Diagnostics" / "import.ir.json").read_text(encoding="utf-8"))
            candidates = ir["state_contract_candidates"]
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["state_symbol"], "#SYSTEM:runtime:runners")


if __name__ == "__main__":
    unittest.main()
