from __future__ import annotations

import unittest

from CIC import import_files
from CIC.function_equivalence import compare_python_fixture


class CICFeatureParityTests(unittest.TestCase):
    def test_python_import_alias_call_resolves(self) -> None:
        bundle = import_files([
            {"path": "lib.py", "content": "def target():\n    return True\n"},
            {"path": "app.py", "content": "import lib as api\n\ndef run():\n    return api.target()\n"},
        ])
        calls = bundle.ir["call_evidence"]
        resolved = [item for item in calls if item.get("source_function_ref") == "FUNCTION::#FILE:app::run"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["resolution_status"], "RESOLVED")
        self.assertEqual(resolved[0]["target_function_ref"], "FUNCTION::#FILE:lib::target")

    def test_shadowed_import_name_does_not_resolve(self) -> None:
        bundle = import_files([
            {"path": "lib.py", "content": "def target():\n    return True\n"},
            {"path": "app.py", "content": "from lib import target\n\ndef run(target):\n    return target()\n"},
        ])
        calls = [item for item in bundle.ir["call_evidence"] if item.get("source_function_ref") == "FUNCTION::#FILE:app::run"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["resolution_status"], "UNRESOLVED")
        self.assertIn("target", calls[0]["shadowed_names"])

    def test_javascript_namespace_call_resolves(self) -> None:
        bundle = import_files([
            {"path": "lib.js", "content": "export function target() { return true; }\n"},
            {"path": "app.js", "content": "import * as api from './lib.js';\nexport function run() { return api.target(); }\n"},
        ])
        calls = [item for item in bundle.ir["call_evidence"] if item.get("source_function_ref") == "FUNCTION::#FILE:app::run"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["resolution_status"], "RESOLVED")
        self.assertEqual(calls[0]["target_function_ref"], "FUNCTION::#FILE:lib::target")

    def test_python_primitive_equivalence(self) -> None:
        source = "def choose(flag: bool):\n    if flag:\n        return True\n    return False\n"
        result = compare_python_fixture(source, "choose", [{"flag": True}, {"flag": False}])
        self.assertEqual(result.status, "EQUIVALENT")
        self.assertEqual(result.decomposition_state, "complete")


if __name__ == "__main__":
    unittest.main()
