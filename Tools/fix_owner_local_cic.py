#!/usr/bin/env python3
from pathlib import Path

pipeline = Path('tools/CIC/package_pipeline.py')
s = pipeline.read_text(encoding='utf-8')
s = s.replace('''def _asset_property(entity_ref: str, asset_ref: str, file_type_ref: str) -> dict[str, Any]:
    return {
        "id": f"ASSET::{entity_ref}",
''','''def _asset_property(entity_ref: str, asset_ref: str, file_type_ref: str) -> dict[str, Any]:
    return {
        "id": "ASSET",
''')
s = s.replace('''    dr_path = format_root / "DR.json"
    dr = _read_json(dr_path)
    dependencies = _dependency_properties(ir)
''','''    dr_path = format_root / "DR.json"
    dr = _read_json(dr_path)
    ccf = _read_json(format_root / "CCF.json")
    ccf_version = ccf.get("version")
    if not isinstance(ccf_version, str) or not ccf_version:
        raise CICPackageError("Format/CCF.json version missing")
    dependencies = _dependency_properties(ir)
''')
s = s.replace('''    manifest["format"] = {"contract_format": "CANONICAL_CONTRACT", "format_version": "2.4.3"}
''','''    manifest["format"] = {"contract_format": "CANONICAL_CONTRACT", "format_version": ccf_version}
''')
pipeline.write_text(s, encoding='utf-8')

cw = Path('tools/CIC/cw.py')
s = cw.read_text(encoding='utf-8')
s = s.replace('''def validate_cw(document: dict[str, Any]) -> dict[str, Any]:
    """Validate lossless Model representation and package-global identity closure only."""
''','''def validate_cw(document: dict[str, Any]) -> dict[str, Any]:
    """Validate lossless Model representation with global Entity and owner-local Property identity."""
''')
s = s.replace('''    identities: set[str] = set()
    for entity in entities:
''','''    entity_ids: set[str] = set()
    for entity in entities:
''')
s = s.replace('''        if entity_id in identities:
            raise CWValidationError(f"duplicate canonical identity: {entity_id}")
        identities.add(entity_id)
        properties = entity.get("properties")
''','''        if entity_id in entity_ids:
            raise CWValidationError(f"duplicate canonical Entity identity: {entity_id}")
        entity_ids.add(entity_id)
        properties = entity.get("properties")
''')
s = s.replace('''        for prop in properties:
            if not isinstance(prop, dict):
                raise CWValidationError(f"CW entity {entity_id} contains non-object Property")
            prop_id = prop.get("id")
            if not isinstance(prop_id, str) or not prop_id:
                raise CWValidationError(f"CW entity {entity_id} Property id missing")
            if prop_id in identities:
                raise CWValidationError(f"duplicate canonical identity: {prop_id}")
            identities.add(prop_id)
''','''        property_ids: set[str] = set()
        for prop in properties:
            if not isinstance(prop, dict):
                raise CWValidationError(f"CW entity {entity_id} contains non-object Property")
            prop_id = prop.get("id")
            if not isinstance(prop_id, str) or not prop_id:
                raise CWValidationError(f"CW entity {entity_id} Property id missing")
            if prop_id in property_ids:
                raise CWValidationError(f"duplicate Property identity inside {entity_id}: {prop_id}")
            property_ids.add(prop_id)
''')
cw.write_text(s, encoding='utf-8')
print('owner-local CIC patch applied')
