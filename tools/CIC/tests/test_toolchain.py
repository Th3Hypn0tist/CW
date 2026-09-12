from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from CIC import import_folder, ingest_cw, validate_toolchain
from CIC.cw_version import verify_cw_versions


class CICToolchainTests(unittest.TestCase):
    def test_validate_import_validate_stamp_chain(self) -> None:
        report = validate_toolchain()
        self.assertEqual(report["result"], "READY")
        self.assertEqual(report["authority"], "package_local_format")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            target = root / "cw"
            source.mkdir()
            (source / "a.py").write_text(
                "def a(flag: bool):\n    if flag:\n        return True\n    return False\n",
                encoding="utf-8",
            )
            result = import_folder(source, target, validate_tools=False)
            self.assertTrue((target / "Format" / "CW.json").is_file())
            self.assertEqual(result.cw_path, target / "Model" / "model.cw")
            self.assertEqual(result.ir_path, target / "Diagnostics" / "import.ir.json")
            document = ingest_cw(target)
            verify_cw_versions(document)
            self.assertEqual(document.get("specification_ref"), "LOCAL_FORMAT:Format")
            self.assertTrue(all(entity.get("timestamp") and entity.get("hash") for entity in document["entities"]))

    def test_force_preserves_unchanged_and_versions_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            target = root / "cw"
            source.mkdir()
            (source / "a.py").write_text("def a():\n    return True\n", encoding="utf-8")
            (source / "b.py").write_text("def b():\n    return True\n", encoding="utf-8")
            import_folder(source, target)
            before = ingest_cw(target)
            versions = {e["id"]: (e["timestamp"], e["hash"]) for e in before["entities"]}
            import_folder(source, target, force=True)
            same = ingest_cw(target)
            self.assertEqual({e["id"]: (e["timestamp"], e["hash"]) for e in same["entities"]}, versions)
            (source / "b.py").write_text("def b():\n    return False\n", encoding="utf-8")
            import_folder(source, target, force=True)
            after = ingest_cw(target)
            after_versions = {e["id"]: (e["timestamp"], e["hash"]) for e in after["entities"]}
            self.assertEqual(after_versions["#FILE:a"], versions["#FILE:a"])
            self.assertNotEqual(after_versions["#FILE:b"][1], versions["#FILE:b"][1])

    def test_asset_byte_change_versions_owner_even_when_parsed_shape_is_same(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            target = root / "cw"
            source.mkdir()
            (source / "notes.weird").write_text("first\n", encoding="utf-8")
            import_folder(source, target)
            before = ingest_cw(target)
            old = before["entities"][0]
            (source / "notes.weird").write_text("second\n", encoding="utf-8")
            import_folder(source, target, force=True)
            after = ingest_cw(target)
            new = after["entities"][0]
            self.assertEqual(old["id"], new["id"])
            self.assertNotEqual(old["hash"], new["hash"])

    def test_resolved_internal_import_becomes_dependency_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            target = root / "cw"
            source.mkdir()
            (source / "lib.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "app.py").write_text("import lib\n", encoding="utf-8")
            import_folder(source, target)
            document = ingest_cw(target)
            app = next(entity for entity in document["entities"] if entity["id"] == "#FILE:app")
            links = [prop for prop in app["properties"] if prop.get("property_type_ref") == "link"]
            dependency = next(prop for prop in links if prop["value"].get("link_type_ref") == "dependency")
            self.assertEqual(dependency["value"]["parent_ref"], "#FILE:lib")
            self.assertEqual(dependency["value"]["child_ref"], "#FILE:app")

    def test_failed_force_keeps_previous_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            target = root / "cw"
            source.mkdir()
            (source / "a.py").write_text("def a():\n    return True\n", encoding="utf-8")
            import_folder(source, target)
            before = copy.deepcopy(ingest_cw(target))
            (source / "a.js").write_text("export function a() { return true; }\n", encoding="utf-8")
            with self.assertRaises(Exception):
                import_folder(source, target, force=True)
            self.assertEqual(ingest_cw(target), before)

    def test_rejects_output_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            source.mkdir()
            (source / "a.py").write_text("def a():\n    return True\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inside the code folder"):
                import_folder(source, source / "generated-cw")

    def test_rejects_output_that_contains_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "out"
            source = target / "src"
            source.mkdir(parents=True)
            (source / "a.py").write_text("def a():\n    return True\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot contain the code folder"):
                import_folder(source, target)


if __name__ == "__main__":
    unittest.main()
