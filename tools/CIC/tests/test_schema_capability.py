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
            "schema_types": ["record", "string", "list"],
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

    def test_explicit_integer_schema_type_closes_observed_gap(self) -> None:
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
            "version": "4.0.5-reference",
            "schema_types": ["record", "string", "integer", "list"],
            "schema_semantics": {
                "record": "record",
                "string": "string",
                "integer": "integer",
                "list": "list",
            },
        }
        report = audit_schema_capabilities(ir, dr)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["summary"]["unsupported_fields"], 0)
        self.assertIn("integer", report["supported_schema_semantics"])

    def test_map_container_is_reported_from_state_contract_evidence(self) -> None:
        ir = {
            "state_contract_candidates": [
                {
                    "source_entity_ref": "#FILE:system:runtime:runner_store",
                    "state_symbol": "#SYSTEM:runtime:runners",
                    "observed_container_types": ["map"],
                }
            ]
        }
        dr = {
            "version": "4.0.5-reference",
            "schema_types": ["record", "string", "integer", "list"],
            "schema_semantics": {},
        }
        report = audit_schema_capabilities(ir, dr)
        self.assertEqual(report["summary"]["state_contracts"], 1)
        self.assertEqual(report["summary"]["unsupported_types"], ["map"])
        self.assertEqual(report["findings"][0]["code"], "SCHEMA_CONTAINER_UNSUPPORTED")
        self.assertEqual(report["findings"][0]["source_contract"], "#SYSTEM:runtime:runners")

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
