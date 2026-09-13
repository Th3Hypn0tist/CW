from __future__ import annotations

import unittest

from linter.cw_condition_validate import validate_event_condition_value


RULESET = {
    "supported_condition_modes": ["ready", "value_equals"],
    "mode_fields": {
        "ready": {"required": [], "forbidden": ["expected_value"]},
        "value_equals": {"required": ["expected_value"], "forbidden": []},
    },
    "expected_value_types": ["boolean", "integer", "string"],
}


class EventConditionValidationTests(unittest.TestCase):
    def test_value_equals_accepts_boolean_integer_and_string_literals(self) -> None:
        for expected in (True, False, 0, 42, "allow", "deny"):
            with self.subTest(expected=expected):
                findings = validate_event_condition_value(
                    {"condition_mode": "value_equals", "expected_value": expected},
                    RULESET,
                )
                self.assertEqual(findings, [])

    def test_value_equals_requires_explicit_expected_value(self) -> None:
        findings = validate_event_condition_value(
            {"condition_mode": "value_equals"},
            RULESET,
        )
        self.assertEqual(findings[0]["code"], "EVENT_CONDITION_FIELD_REQUIRED")

    def test_ready_cannot_carry_expected_value(self) -> None:
        findings = validate_event_condition_value(
            {"condition_mode": "ready", "expected_value": True},
            RULESET,
        )
        self.assertEqual(findings[0]["code"], "EVENT_CONDITION_FIELD_FORBIDDEN")

    def test_value_equals_rejects_composite_or_null_expected_values(self) -> None:
        for expected in (None, [], {}, 1.5):
            with self.subTest(expected=expected):
                findings = validate_event_condition_value(
                    {"condition_mode": "value_equals", "expected_value": expected},
                    RULESET,
                )
                self.assertEqual(
                    findings[0]["code"],
                    "EVENT_CONDITION_EXPECTED_VALUE_TYPE_INVALID",
                )

    def test_boolean_is_not_collapsed_into_integer(self) -> None:
        integer_only = dict(RULESET)
        integer_only["expected_value_types"] = ["integer"]
        findings = validate_event_condition_value(
            {"condition_mode": "value_equals", "expected_value": True},
            integer_only,
        )
        self.assertEqual(
            findings[0]["code"],
            "EVENT_CONDITION_EXPECTED_VALUE_TYPE_INVALID",
        )

    def test_unknown_mode_is_invalid(self) -> None:
        findings = validate_event_condition_value(
            {"condition_mode": "predicate", "expected_value": True},
            RULESET,
        )
        self.assertEqual(findings[0]["code"], "EVENT_CONDITION_MODE_INVALID")


if __name__ == "__main__":
    unittest.main()
