from __future__ import annotations

import unittest

from CIC.schema_capability import audit_schema_capabilities


class CICSchemaCapabilityTests(unittest.TestCase):
    def test_integer_field_is_reported_when_dr_does_not_define_integer(self) -> None:
        ir = {
            "record_contract_candidates": [
                {
                    "source_entity_ref": "#FILE:types",
                    "source_class": "TriggerDef",
                    "serialized_fields": [
                        {"name": "kind", "observed_type": "string"},
                        {"name": "pulse_ms", "observed_type": "integer"},
                    ],
                }
            ]
        }
        dr = {
            "version": "test",
            "schema_semantics": {
                "record": "record",
                "string": "string",
                "list": "list",
            },
        }
        report = audit_schema_capabilities(ir, dr)
        self.assertEqual(report["summary"]["unsupported_fields"], 1)
        self.assertEqual(report["summary"]["unsupported_types"], ["integer"])
        self.assertEqual(report["findings"][0]["field"], "pulse_ms")
        self.assertFalse(report["findings"][0]["ccf_change_required"])

    def test_supported_observed_types_produce_no_findings(self) -> None:
        ir = {
            "record_contract_candidates": [
                {
                    "source_entity_ref": "#FILE:types",
                    "source_class": "EventDef",
                    "serialized_fields": [
                        {"name": "trigger", "observed_type": "string"},
                        {"name": "command", "observed_type": "string"},
                    ],
                }
            ]
        }
        dr = {"schema_semantics": {"record": "", "string": "", "list": ""}}
        report = audit_schema_capabilities(ir, dr)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["summary"]["unsupported_fields"], 0)


if __name__ == "__main__":
    unittest.main()
