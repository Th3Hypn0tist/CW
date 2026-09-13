from __future__ import annotations

import unittest

from linter.cw_dispatch_validate import resolve_event_dispatch, validate_emit_statement, validate_event_dispatch_link


class EventDispatchValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.domain = {
            "id": "#ABS:DispatchDomain",
            "properties": [
                {
                    "id": "MEMBERS::#ABS:DispatchDomain",
                    "property_type_ref": "members",
                    "value": {"member_refs": ["#FILE:a", "#FILE:b"], "properties": {}},
                }
            ],
        }
        self.entities = {
            "#ABS:DispatchDomain": self.domain,
            "#FILE:a": {"id": "#FILE:a", "properties": []},
            "#FILE:b": {"id": "#FILE:b", "properties": []},
            "#FILE:outside": {"id": "#FILE:outside", "properties": []},
        }
        self.properties = {
            "DATA_SELECTOR": {"id": "DATA_SELECTOR", "property_type_ref": "data", "value": {}},
            "EVENT_A": {"id": "EVENT_A", "property_type_ref": "event", "value": {}},
            "EVENT_OUTSIDE": {"id": "EVENT_OUTSIDE", "property_type_ref": "event", "value": {}},
            "DATA_NOT_EVENT": {"id": "DATA_NOT_EVENT", "property_type_ref": "data", "value": {}},
            "FUNCTION_SOURCE": {"id": "FUNCTION_SOURCE", "property_type_ref": "function", "value": {}},
            "LINK_DISPATCH": {
                "id": "LINK_DISPATCH",
                "property_type_ref": "link",
                "value": {
                    "link_type_ref": "event_dispatch",
                    "parent_ref": "FUNCTION_SOURCE",
                    "child_ref": "#ABS:DispatchDomain",
                    "selector_ref": "DATA_SELECTOR",
                },
            },
            "LINK_CAUSE": {
                "id": "LINK_CAUSE",
                "property_type_ref": "link",
                "value": {
                    "link_type_ref": "event_cause",
                    "parent_ref": "FUNCTION_SOURCE",
                    "child_ref": "EVENT_A",
                },
            },
        }
        self.owners = {
            "DATA_SELECTOR": "#FILE:a",
            "EVENT_A": "#FILE:a",
            "EVENT_OUTSIDE": "#FILE:outside",
            "DATA_NOT_EVENT": "#FILE:a",
            "FUNCTION_SOURCE": "#FILE:a",
            "LINK_DISPATCH": "#FILE:a",
            "LINK_CAUSE": "#FILE:a",
        }
        self.dispatch_value = self.properties["LINK_DISPATCH"]["value"]

    def test_ready_exact_event_id_inside_domain_resolves(self) -> None:
        result = resolve_event_dispatch(
            dispatch_value=self.dispatch_value,
            selector_state="READY",
            selector_value="EVENT_A",
            properties=self.properties,
            owners=self.owners,
            entities=self.entities,
        )
        self.assertEqual(result["state"], "READY")
        self.assertEqual(result["result"], "EVENT_A")

    def test_alias_or_command_token_is_not_interpreted(self) -> None:
        result = resolve_event_dispatch(
            dispatch_value=self.dispatch_value,
            selector_state="READY",
            selector_value="q",
            properties=self.properties,
            owners=self.owners,
            entities=self.entities,
        )
        self.assertEqual(result["state"], "INVALID")
        self.assertEqual(result["finding"]["code"], "EVENT_DISPATCH_TARGET_UNRESOLVED")

    def test_non_event_target_is_invalid(self) -> None:
        result = resolve_event_dispatch(
            dispatch_value=self.dispatch_value,
            selector_state="READY",
            selector_value="DATA_NOT_EVENT",
            properties=self.properties,
            owners=self.owners,
            entities=self.entities,
        )
        self.assertEqual(result["finding"]["code"], "EVENT_DISPATCH_TARGET_NOT_EVENT")

    def test_event_outside_domain_is_invalid(self) -> None:
        result = resolve_event_dispatch(
            dispatch_value=self.dispatch_value,
            selector_state="READY",
            selector_value="EVENT_OUTSIDE",
            properties=self.properties,
            owners=self.owners,
            entities=self.entities,
        )
        self.assertEqual(result["finding"]["code"], "EVENT_DISPATCH_TARGET_OUTSIDE_DOMAIN")

    def test_unready_selector_is_invalid_not_false_or_noop(self) -> None:
        for state in ("UNBOUND", "INVALID"):
            with self.subTest(state=state):
                result = resolve_event_dispatch(
                    dispatch_value=self.dispatch_value,
                    selector_state=state,
                    selector_value="EVENT_A",
                    properties=self.properties,
                    owners=self.owners,
                    entities=self.entities,
                )
                self.assertEqual(result["state"], "INVALID")
                self.assertEqual(result["finding"]["code"], "EVENT_DISPATCH_SELECTOR_NOT_READY")

    def test_selector_ref_must_be_data(self) -> None:
        bad = dict(self.dispatch_value)
        bad["selector_ref"] = "EVENT_A"
        findings = validate_event_dispatch_link(bad, self.properties, self.entities)
        self.assertEqual(findings[0]["code"], "EVENT_DISPATCH_SELECTOR_INVALID")

    def test_domain_requires_exactly_one_members_surface(self) -> None:
        self.entities["#ABS:DispatchDomain"] = {"id": "#ABS:DispatchDomain", "properties": []}
        findings = validate_event_dispatch_link(self.dispatch_value, self.properties, self.entities)
        self.assertEqual(findings[0]["code"], "DISPATCH_DOMAIN_MEMBERS_INVALID")

    def test_emit_accepts_static_or_dynamic_route_but_not_both(self) -> None:
        dynamic = validate_emit_statement(
            {"op": "emit", "dispatch_ref": "LINK_DISPATCH"},
            containing_function_ref="FUNCTION_SOURCE",
            properties=self.properties,
        )
        self.assertEqual(dynamic, [])

        static = validate_emit_statement(
            {"op": "emit", "cause_ref": "LINK_CAUSE"},
            containing_function_ref="FUNCTION_SOURCE",
            properties=self.properties,
        )
        self.assertEqual(static, [])

        both = validate_emit_statement(
            {"op": "emit", "cause_ref": "LINK_CAUSE", "dispatch_ref": "LINK_DISPATCH"},
            containing_function_ref="FUNCTION_SOURCE",
            properties=self.properties,
        )
        self.assertEqual(both[0]["code"], "EMIT_ROUTE_CARDINALITY_INVALID")

        neither = validate_emit_statement(
            {"op": "emit"},
            containing_function_ref="FUNCTION_SOURCE",
            properties=self.properties,
        )
        self.assertEqual(neither[0]["code"], "EMIT_ROUTE_CARDINALITY_INVALID")


if __name__ == "__main__":
    unittest.main()
