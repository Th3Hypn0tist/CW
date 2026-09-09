from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tools.CIC import import_folder, ingest_cw, validate_toolchain
from tools.CIC.cw_version import verify_cw_versions


class CICToolchainTests(unittest.TestCase):
    def test_validate_import_validate_stamp_chain(self) -> None:
        validate_toolchain()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"src"; target=root/"cw"; source.mkdir()
            (source/"a.py").write_text("def a(flag: bool):\n    if flag:\n        return True\n    return False\n",encoding="utf-8")
            result=import_folder(source,target,validate_tools=False)
            self.assertEqual(result.files_imported,1)
            document=ingest_cw(target); verify_cw_versions(document)
            self.assertNotIn("specification_ref",document)
            self.assertTrue(all(entity.get("timestamp") and entity.get("hash") for entity in document["entities"]))

    def test_force_preserves_unchanged_and_versions_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"src"; target=root/"cw"; source.mkdir()
            (source/"a.py").write_text("def a():\n    return True\n",encoding="utf-8")
            (source/"b.py").write_text("def b():\n    return True\n",encoding="utf-8")
            import_folder(source,target)
            before=ingest_cw(target); versions={e["id"]:(e["timestamp"],e["hash"]) for e in before["entities"]}
            import_folder(source,target,force=True)
            same=ingest_cw(target); self.assertEqual({e["id"]:(e["timestamp"],e["hash"]) for e in same["entities"]},versions)
            (source/"b.py").write_text("def b():\n    return False\n",encoding="utf-8")
            import_folder(source,target,force=True)
            after=ingest_cw(target); after_versions={e["id"]:(e["timestamp"],e["hash"]) for e in after["entities"]}
            self.assertEqual(after_versions["#FILE:a"],versions["#FILE:a"])
            self.assertNotEqual(after_versions["#FILE:b"][1],versions["#FILE:b"][1])

    def test_failed_force_keeps_previous_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"src"; target=root/"cw"; source.mkdir()
            (source/"a.py").write_text("def a():\n    return True\n",encoding="utf-8")
            import_folder(source,target); before=copy.deepcopy(ingest_cw(target))
            (source/"a.js").write_text("export function a() { return true; }\n",encoding="utf-8")
            with self.assertRaises(Exception): import_folder(source,target,force=True)
            self.assertEqual(ingest_cw(target),before)

    def test_rejects_output_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"src"; source.mkdir()
            (source/"a.py").write_text("def a():\n    return True\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"inside the code folder"):
                import_folder(source,source/"generated-cw")

    def test_rejects_output_that_contains_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=root/"out"; source=target/"src"; source.mkdir(parents=True)
            (source/"a.py").write_text("def a():\n    return True\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"cannot contain the code folder"):
                import_folder(source,target)


if __name__=="__main__": unittest.main()
