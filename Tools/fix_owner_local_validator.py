#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "linter" / "cw_validate.py"
text = path.read_text(encoding="utf-8")
text = text.replace(
'''                            ref_path = property_path + f".value.{field}[{ref_index}]"\n                            target = resolve_ref(ref, None, objects)\n                            if target is None:\n                                c.u("CANONICAL_REFERENCE_UNRESOLVED", file, ref_path, repr(ref))''',
'''                            ref_path = property_path + f".value.{field}[{ref_index}]"\n                            target = resolve_ref(ref, owner_id, objects)\n                            if target is None:\n                                c.u("CANONICAL_REFERENCE_UNRESOLVED", file, ref_path, repr(ref))''')
text = text.replace(
'''                        for side in ("parent_ref", "child_ref"):\n                            ref = value.get(side)\n                            target = resolve_ref(ref, None, objects)\n                            if target is None:\n                                c.u("LINK_ENDPOINT_UNRESOLVED", file, property_path + ".value." + side, repr(ref))''',
'''                        for side in ("parent_ref", "child_ref"):\n                            ref = value.get(side)\n                            target = resolve_ref(ref, owner_id, objects)\n                            if target is None:\n                                c.u("LINK_ENDPOINT_UNRESOLVED", file, property_path + ".value." + side, repr(ref))''')
path.write_text(text, encoding="utf-8")
print("owner-aware validator lookup patch applied")
