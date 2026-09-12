from __future__ import annotations

import unittest

from CIC import import_files
from CIC.profiles import profile_options


class CICRegistrationEventTests(unittest.TestCase):
    def test_aigmos_commanddef_registration_maps_to_handler_event(self) -> None:
        source = """from dataclasses import dataclass

@dataclass
class CommandDef:
    command: str
    handler: object
    help_short: str
    help_full: str

command = 'q'
help_short = 'query'
help_full = 'query help'

def handler(line: str, parser):
    return None

def register() -> CommandDef:
    return CommandDef(
        command=command,
        handler=handler,
        help_short=help_short,
        help_full=help_full,
    )
"""
        rules = profile_options("aigmos")["event_rules"]
        bundle = import_files(
            [{"path": "system/cs/commands/q.py", "content": source}],
            event_rules=rules,
            materialize_events=True,
        )

        candidates = bundle.ir["event_candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["function_qualified_name"], "handler")
        self.assertEqual(candidates[0]["event_type_ref"], "command")
        self.assertEqual(candidates[0]["trigger_evidence_kind"], "registration_handler")
        self.assertEqual(candidates[0]["trigger_evidence_value"], "CommandDef")

        entity = bundle.cw["entities"][0]
        functions = {
            prop["id"]: prop
            for prop in entity["properties"]
            if prop.get("property_type_ref") == "function"
        }
        events = [prop for prop in entity["properties"] if prop.get("property_type_ref") == "event"]
        handlers = [
            prop
            for prop in entity["properties"]
            if prop.get("property_type_ref") == "link"
            and prop.get("value", {}).get("link_type_ref") == "event_handler"
        ]
        self.assertIn("FUNCTION::#FILE:system:cs:commands:q::handler", functions)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["value"]["event_type_ref"], "command")
        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0]["value"]["parent_ref"], events[0]["id"])
        self.assertEqual(
            handlers[0]["value"]["child_ref"],
            "FUNCTION::#FILE:system:cs:commands:q::handler",
        )

    def test_registration_rule_does_not_guess_from_function_names(self) -> None:
        source = """def handler(line, parser):
    return None

def register():
    return handler
"""
        rules = profile_options("aigmos")["event_rules"]
        bundle = import_files(
            [{"path": "plain.py", "content": source}],
            event_rules=rules,
            materialize_events=True,
        )
        self.assertEqual(bundle.ir["event_candidates"], [])
        entity = bundle.cw["entities"][0]
        self.assertFalse(any(prop.get("property_type_ref") == "event" for prop in entity["properties"]))

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown CIC profile"):
            profile_options("not-a-profile")


if __name__ == "__main__":
    unittest.main()
