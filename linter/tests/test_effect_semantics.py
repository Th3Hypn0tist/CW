from __future__ import annotations

import json
import unittest
from pathlib import Path

from linter.cw_effect_validate import validate_effect_semantics


DR_PATH = Path(__file__).resolve().parents[2] / "Examples" / "Ultralight_CMS" / "Format" / "DR.json"


class EffectSemanticValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dr = json.loads(DR_PATH.read_text(encoding="utf-8"))

    def test_filesystem_write_requires_explicit_target(self) -> None:
        valid = validate_effect_semantics(
            {"effect_type_ref": "filesystem_mutation", "operation": "write", "input_refs": ["DATA_CONTENT"]},
            [{"target_role": "target"}],
            self.dr,
        )
        self.assertEqual(valid, [])

        invalid = validate_effect_semantics(
            {"effect_type_ref": "filesystem_mutation", "operation": "write", "input_refs": ["DATA_CONTENT"]},
            [],
            self.dr,
        )
        self.assertEqual(invalid[0]["code"], "EFFECT_TARGET_ROLE_CARDINALITY_INVALID")

    def test_filesystem_move_requires_source_and_destination(self) -> None:
        findings = validate_effect_semantics(
            {"effect_type_ref": "filesystem_mutation", "operation": "move"},
            [{"target_role": "source"}, {"target_role": "destination"}],
            self.dr,
        )
        self.assertEqual(findings, [])

        missing_destination = validate_effect_semantics(
            {"effect_type_ref": "filesystem_mutation", "operation": "move"},
            [{"target_role": "source"}],
            self.dr,
        )
        self.assertEqual(missing_destination[0]["code"], "EFFECT_TARGET_ROLE_CARDINALITY_INVALID")

    def test_persistence_is_backend_neutral_but_targets_are_explicit(self) -> None:
        findings = validate_effect_semantics(
            {"effect_type_ref": "persistence_mutation", "operation": "set", "input_refs": ["DATA_VALUE"]},
            [{"target_role": "backend"}, {"target_role": "target"}],
            self.dr,
        )
        self.assertEqual(findings, [])

        duplicate_backend = validate_effect_semantics(
            {"effect_type_ref": "persistence_mutation", "operation": "batch", "input_refs": ["DATA_BATCH"]},
            [{"target_role": "backend"}, {"target_role": "backend"}, {"target_role": "target"}],
            self.dr,
        )
        self.assertEqual(duplicate_backend[0]["code"], "EFFECT_TARGET_ROLE_CARDINALITY_INVALID")

    def test_network_io_is_outbound_only_and_requires_payload(self) -> None:
        valid = validate_effect_semantics(
            {"effect_type_ref": "network_io", "operation": "send", "input_refs": ["DATA_PAYLOAD"]},
            [{"target_role": "endpoint"}],
            self.dr,
        )
        self.assertEqual(valid, [])

        receive = validate_effect_semantics(
            {"effect_type_ref": "network_io", "operation": "receive", "input_refs": ["DATA_PAYLOAD"]},
            [{"target_role": "endpoint"}],
            self.dr,
        )
        self.assertEqual(receive[0]["code"], "EFFECT_OPERATION_INVALID")

        no_payload = validate_effect_semantics(
            {"effect_type_ref": "network_io", "operation": "respond"},
            [{"target_role": "endpoint"}],
            self.dr,
        )
        self.assertEqual(no_payload[0]["code"], "EFFECT_INPUT_CARDINALITY_UNSATISFIED")

    def test_resource_lifecycle_requires_explicit_resource(self) -> None:
        for operation in ("start", "stop", "close", "join"):
            with self.subTest(operation=operation):
                findings = validate_effect_semantics(
                    {"effect_type_ref": "resource_lifecycle", "operation": operation},
                    [{"target_role": "resource"}],
                    self.dr,
                )
                self.assertEqual(findings, [])

    def test_unknown_operation_and_unknown_effect_type_are_invalid(self) -> None:
        bad_operation = validate_effect_semantics(
            {"effect_type_ref": "filesystem_mutation", "operation": "chmod"},
            [{"target_role": "target"}],
            self.dr,
        )
        self.assertEqual(bad_operation[0]["code"], "EFFECT_OPERATION_INVALID")

        bad_type = validate_effect_semantics(
            {"effect_type_ref": "arbitrary_runtime_action", "operation": "run"},
            [],
            self.dr,
        )
        self.assertEqual(bad_type[0]["code"], "EFFECT_TYPE_UNREGISTERED")


if __name__ == "__main__":
    unittest.main()
