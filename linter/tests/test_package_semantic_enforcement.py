from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from linter.cw_package_validate import validate_package


GOLDEN = Path(__file__).resolve().parents[2] / "Examples" / "Ultralight_CMS"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


class PackageSemanticEnforcementTests(unittest.TestCase):
    def _copy_golden(self, root: Path) -> Path:
        target = root / "package"
        shutil.copytree(GOLDEN, target)
        return target

    def test_golden_remains_ready(self) -> None:
        report = validate_package(GOLDEN)
        self.assertEqual(report["result"], "READY", report["findings"])

    def test_ready_condition_rejects_expected_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = self._copy_golden(Path(tmp))
            renderer = package / "Model" / "FILE" / "renderer.cw"
            model = _read(renderer)
            condition = next(
                item for item in model["properties"]
                if item.get("id") == "LINK_RENDER_REQUEST_READY"
            )
            condition["value"]["expected_value"] = True
            _write(renderer, model)
            report = validate_package(package)
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("EVENT_CONDITION_FIELD_FORBIDDEN", codes)

    def test_unknown_effect_type_invalidates_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = self._copy_golden(Path(tmp))
            renderer = package / "Model" / "FILE" / "renderer.cw"
            model = _read(renderer)
            effect = next(
                item for item in model["properties"]
                if item.get("id") == "EFFECT_PUBLISH_DOCUMENT"
            )
            effect["value"]["effect_type_ref"] = "arbitrary_runtime_action"
            _write(renderer, model)
            report = validate_package(package)
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("EFFECT_TYPE_UNREGISTERED", codes)

    def test_unbounded_event_dispatch_invalidates_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = self._copy_golden(Path(tmp))
            renderer = package / "Model" / "FILE" / "renderer.cw"
            model = _read(renderer)
            link = next(
                item for item in model["properties"]
                if item.get("id") == "LINK_OPEN_PAGE_CAUSES_RENDER_PAGE"
            )
            link["ruleset_ref"] = "RULESET_LINK_EVENT_DISPATCH"
            link["value"] = {
                "link_type_ref": "event_dispatch",
                "parent_ref": "FUNCTION_OPEN_PAGE",
                "child_ref": "#FILE:renderer",
                "selector_ref": "EVENT_RENDER_PAGE",
                "properties": {},
            }
            _write(renderer, model)
            report = validate_package(package)
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("EVENT_DISPATCH_SELECTOR_INVALID", codes)
            self.assertIn("DISPATCH_DOMAIN_MEMBERS_INVALID", codes)


if __name__ == "__main__":
    unittest.main()
