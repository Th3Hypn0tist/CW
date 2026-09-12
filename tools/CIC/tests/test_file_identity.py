from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from CIC import import_folder, ingest_cw
from CIC.identity import CICIdentityError


class CICFileIdentityTests(unittest.TestCase):
    def _import(self, files: dict[str, str]) -> tuple[dict, dict, Path]:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        base = Path(holder.name)
        root = base / "source"
        output = base / "cw"
        root.mkdir()
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        result = import_folder(root, output)
        cw = ingest_cw(output)
        ir = json.loads(result.ir_path.read_text(encoding="utf-8"))
        return cw, ir, output

    def _file_refs(self, cw: dict) -> list[str]:
        return [
            entity["id"]
            for entity in cw.get("entities", [])
            if isinstance(entity, dict) and isinstance(entity.get("id"), str) and entity["id"].startswith("#FILE:")
        ]

    def test_CW_FILE_TREE_001_one_source_file_maps_to_language_agnostic_canonical_identity(self):
        cw, ir, output = self._import({"app.py": "VALUE = 1\n"})
        self.assertEqual(self._file_refs(cw), ["#FILE:app"])
        self.assertEqual(ir["files"][0]["file_ref"], "FILE::app.py")
        self.assertEqual(ir["files"][0]["canonical_file_ref"], "#FILE:app")
        self.assertEqual(ir["files"][0]["cw_shard_path"], "FILE/app.cw")
        self.assertTrue((output / "Model" / "FILE" / "app.cw").is_file())
        self.assertFalse((output / "Model" / "FILE" / "app.py.cw").exists())
        self.assertTrue((output / "Format" / "CW.json").is_file())
        self.assertTrue((output / "Assets" / "FILE" / "%23FILE%3Aapp.py").is_file())
        entity = cw["entities"][0]
        self.assertEqual(entity["entity_type_ref"], "FILE")
        assets = [prop for prop in entity["properties"] if prop.get("property_type_ref") == "asset"]
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["value"]["asset_ref"], "Assets/FILE/%23FILE%3Aapp.py")

    def test_CW_FILE_TREE_002_distinct_canonical_paths_do_not_collapse(self):
        cw, _, _ = self._import({"a/common.py": "A = 1\n", "b/common.py": "B = 2\n"})
        refs = self._file_refs(cw)
        self.assertEqual(set(refs), {"#FILE:a:common", "#FILE:b:common"})
        self.assertEqual(len(refs), len(set(refs)))

    def test_CW_FILE_TREE_003_source_language_suffix_collision_is_hard_rejected(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        base = Path(holder.name)
        root = base / "source"
        root.mkdir()
        (root / "foo").mkdir()
        (root / "foo" / "bar.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "foo" / "bar.js").write_text("export const value = 1;\n", encoding="utf-8")
        with self.assertRaisesRegex(CICIdentityError, "canonical #FILE identity collision"):
            import_folder(root, base / "cw")

    def test_CW_FILE_TREE_005_function_is_property_not_entity(self):
        cw, ir, _ = self._import({"service.py": "def handle(value):\n    return value + 1\n"})
        self.assertEqual(self._file_refs(cw), ["#FILE:service"])
        entity = cw["entities"][0]
        functions = [prop for prop in entity.get("properties", []) if prop.get("property_type_ref") == "function"]
        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0]["id"], "FUNCTION::#FILE:service::handle")
        self.assertEqual(functions[0]["value"]["properties"]["owner_file_ref"], "#FILE:service")
        self.assertEqual(functions[0]["value"]["properties"]["source_file_ref"], "FILE::service.py")
        self.assertEqual(functions[0]["value"]["properties"]["source_language"], "python")
        self.assertFalse(any(item.get("file_ref", "").startswith("FUNCTION::") for item in ir.get("files", [])))

    def test_CW_FILE_TREE_008_unknown_text_file_is_preserved_as_registered_package_asset(self):
        cw, ir, output = self._import({"notes.weird": "hello\n"})
        self.assertEqual(self._file_refs(cw), ["#FILE:notes"])
        self.assertEqual(ir["files"][0]["file_ref"], "FILE::notes.weird")
        self.assertEqual(ir["files"][0]["language_ir"]["language_id"], "unclassified")
        self.assertEqual(ir["files"][0]["language_ir"]["diagnostics"][0]["code"], "LANGUAGE_UNCLASSIFIED")
        self.assertTrue((output / "Model" / "FILE" / "notes.cw").is_file())
        self.assertTrue((output / "Assets" / "FILE" / "%23FILE%3Anotes.weird").is_file())
        dr = json.loads((output / "Format" / "DR.json").read_text(encoding="utf-8"))
        self.assertTrue(any(item.get("extensions") == [".weird"] for item in dr["asset_file_types"]))

    def test_CW_FILE_TREE_010_excluded_dependency_directory_does_not_enter_tree(self):
        cw, _, _ = self._import({"app.py": "VALUE = 1\n", "node_modules/pkg/index.js": "module.exports = 1;\n"})
        self.assertEqual(self._file_refs(cw), ["#FILE:app"])


if __name__ == "__main__":
    unittest.main()
