from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from CIC import import_folder


class CICModuleDiscoveryTests(unittest.TestCase):
    def test_aigmos_profile_discovers_input_and_adapter_modules_as_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "package"

            files = {
                "system/inputs/registry.py": """_CORE_PACKAGE = 'system.inputs'\n_EXT_PACKAGE = 'extensions.inputs'\n_SKIP_MODULES = {'registry', '__init__'}\n""",
                "system/inputs/__init__.py": "",
                "system/inputs/keyboard.py": "class KeyboardInput:\n    pass\n",
                "extensions/inputs/custom.py": "class CustomInput:\n    pass\n",
                "system/adapters/registry.py": """_CORE_PACKAGE = 'system.adapters'\n_EXT_PACKAGE = 'extensions.adapters'\n_SKIP_MODULES = {'osc', 'registry', '__init__'}\n""",
                "system/adapters/__init__.py": "",
                "system/adapters/mem.py": "class MemAdapter:\n    pass\n",
                "system/adapters/osc.py": "class OscAdapter:\n    pass\n",
                "extensions/adapters/http.py": "class HttpAdapter:\n    pass\n",
            }
            for rel, content in files.items():
                path = source / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            import_folder(source, target, profile="aigmos")
            ir = json.loads((target / "Diagnostics" / "import.ir.json").read_text(encoding="utf-8"))
            candidates = ir["module_candidates"]

            found = {(item["role"], item["source_path"]) for item in candidates}
            self.assertEqual(found, {
                ("input", "system/inputs/keyboard.py"),
                ("input", "extensions/inputs/custom.py"),
                ("adapter", "system/adapters/mem.py"),
                ("adapter", "extensions/adapters/http.py"),
            })
            self.assertTrue(all(item["canonical_ready"] is False for item in candidates))
            self.assertTrue(all(item["canonical_semantic_authority"] is False for item in candidates))
            self.assertFalse(any(item["source_path"].endswith("registry.py") for item in candidates))
            self.assertFalse(any(item["source_path"].endswith("osc.py") for item in candidates))


if __name__ == "__main__":
    unittest.main()
