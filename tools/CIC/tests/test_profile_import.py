from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from CIC import import_folder, ingest_cw


class CICProfileImportTests(unittest.TestCase):
    def test_aigmos_profile_materializes_command_event_in_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "package"
            command_file = source / "system" / "cs" / "commands" / "q.py"
            command_file.parent.mkdir(parents=True)
            command_file.write_text(
                """class CommandDef:
    def __init__(self, command, handler, help_short, help_full):
        self.command = command
        self.handler = handler

command = 'q'
help_short = 'query'
help_full = 'query help'

def handler(line, parser):
    return None

def register():
    return CommandDef(
        command=command,
        handler=handler,
        help_short=help_short,
        help_full=help_full,
    )
""",
                encoding="utf-8",
            )

            import_folder(source, target, profile="aigmos")
            document = ingest_cw(target)
            entity = next(item for item in document["entities"] if item["id"] == "#FILE:system:cs:commands:q")
            events = [prop for prop in entity["properties"] if prop.get("property_type_ref") == "event"]
            handlers = [
                prop
                for prop in entity["properties"]
                if prop.get("property_type_ref") == "link"
                and prop.get("value", {}).get("link_type_ref") == "event_handler"
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["value"]["event_type_ref"], "command")
            self.assertEqual(len(handlers), 1)
            self.assertEqual(handlers[0]["value"]["parent_ref"], events[0]["id"])
            self.assertEqual(
                handlers[0]["value"]["child_ref"],
                "FUNCTION::#FILE:system:cs:commands:q::handler",
            )
            self.assertTrue((target / "Format" / "CW.json").is_file())
            self.assertTrue((target / "Assets" / "FILE").is_dir())


if __name__ == "__main__":
    unittest.main()
