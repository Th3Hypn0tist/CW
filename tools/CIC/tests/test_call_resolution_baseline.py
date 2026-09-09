from __future__ import annotations

import unittest

from CIC import import_files
from CIC.call_resolution import resolve_function_calls


class CICFunctionCallResolutionTests(unittest.TestCase):
    def test_CALL_001_same_file_top_level_call_resolves_function_properties(self):
        bundle = import_files([{"path": "app.py", "content": "def helper():\n    return 1\n\ndef run():\n    return helper()\n"}])
        item = next(call for call in bundle.ir["call_evidence"] if call["source_function_ref"].endswith("::run"))
        self.assertEqual(item["target_function_ref"], "FUNCTION::#FILE:app::helper")
        self.assertEqual(item["resolution_status"], "RESOLVED")
        self.assertFalse(item["canonical_semantic_authority"])

    def test_CALL_002_parent_call_resolves_nested_function_property(self):
        bundle = import_files([{"path": "app.py", "content": "def outer():\n    def inner():\n        return 1\n    return inner()\n"}])
        item = next(call for call in bundle.ir["call_evidence"] if call["source_function_ref"] == "FUNCTION::#FILE:app::outer")
        self.assertEqual(item["target_function_ref"], "FUNCTION::#FILE:app::outer.<locals>.inner")

    def test_CALL_003_python_self_method_resolves_same_class_surface(self):
        bundle = import_files([{"path": "controller.py", "content": "class Controller:\n    def close(self):\n        return True\n    def open(self):\n        return self.close()\n"}])
        item = next(call for call in bundle.ir["call_evidence"] if call["source_function_ref"].endswith("::Controller.open"))
        self.assertEqual(item["target_function_ref"], "FUNCTION::#FILE:controller::Controller.close")

    def test_CALL_004_python_from_import_resolves_target_file_function(self):
        bundle = import_files([
            {"path": "app.py", "content": "from dep import helper as h\n\ndef run():\n    return h()\n"},
            {"path": "dep.py", "content": "def helper():\n    return 1\n"},
        ])
        item = next(call for call in bundle.ir["call_evidence"] if call["source_function_ref"].endswith("::run"))
        self.assertEqual(item["target_function_ref"], "FUNCTION::#FILE:dep::helper")

    def test_CALL_005_python_module_alias_resolves_target_surface(self):
        bundle = import_files([
            {"path": "app.py", "content": "import dep as d\n\ndef run():\n    return d.helper()\n"},
            {"path": "dep.py", "content": "def helper():\n    return 1\n"},
        ])
        item = next(call for call in bundle.ir["call_evidence"] if call["source_function_ref"].endswith("::run"))
        self.assertEqual(item["target_function_ref"], "FUNCTION::#FILE:dep::helper")

    def test_CALL_006_unproven_runtime_call_remains_explicit_unresolved(self):
        bundle = import_files([{"path": "app.py", "content": "def run(cb):\n    return cb()\n"}])
        item = bundle.ir["call_evidence"][0]
        self.assertEqual(item["resolution_status"], "UNRESOLVED")
        self.assertEqual(item["candidate_function_refs"], [])

    def test_CALL_007_call_resolution_never_creates_canonical_link(self):
        bundle = import_files([{"path": "app.py", "content": "def helper():\n    return 1\n\ndef run():\n    return helper()\n"}])
        links = [prop for entity in bundle.cw["entities"] for prop in entity["properties"] if prop.get("property_type_ref") == "link"]
        self.assertEqual(links, [])

    def test_CALL_008_pipeline_evidence_matches_pure_call_resolver(self):
        bundle = import_files([{"path": "app.py", "content": "def helper():\n    return 1\n\ndef run():\n    return helper()\n"}])
        self.assertEqual(bundle.ir["call_evidence"], resolve_function_calls(bundle.ir))

    def test_CALL_009_builtin_js_parser_preserves_unresolved_runtime_call_evidence(self):
        bundle = import_files([{"path": "web/app.js", "content": "export function run() { return helper(); }\n"}])
        item = bundle.ir["call_evidence"][0]
        self.assertEqual(item["source_function_ref"], "FUNCTION::#FILE:web:app::run")
        self.assertEqual(item["target_expression"], "helper")
        self.assertEqual(item["resolution_status"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
