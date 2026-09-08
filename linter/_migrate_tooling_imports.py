#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINTER = ROOT / "linter" / "cw_spec_lint.py"
VALIDATOR = ROOT / "linter" / "cw_validate.py"
README = ROOT / "linter" / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "cw-spec-lint.yml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {text.count(old)}")
    return text.replace(old, new, 1)


def migrate_linter() -> None:
    text = LINTER.read_text(encoding="utf-8")
    text = replace_once(text, 'LINTER_VERSION = "1.0.0"', 'LINTER_VERSION = "1.1.0"', "linter version")
    text = replace_once(
        text,
        'from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple\n',
        'from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple\n\ntry:\n    from .cw_spec_common import SPEC_IDS, classify_spec as classify_core_spec\nexcept ImportError:  # direct script execution\n    from cw_spec_common import SPEC_IDS, classify_spec as classify_core_spec\n',
        "linter shared import",
    )
    text = replace_once(
        text,
        'EXPECTED_IDS = {\n    "ccf": "CANONICAL_CONTRACT_FORMAT",\n    "nodetypes": "CW_NODETYPES",\n    "rulesets": "CW_RULESETS",\n}\n',
        'EXPECTED_IDS = SPEC_IDS\n',
        "expected ids",
    )
    old_classify = '''def classify(data: Any) -> str:\n    if not isinstance(data, dict):\n        return "other"\n    if data.get("type") == "canonical_contract_format" or data.get("id") == "CANONICAL_CONTRACT_FORMAT":\n        return "ccf"\n    if data.get("id") == "CW_NODETYPES" or (\n        isinstance(data.get("nodetypes"), list) and isinstance(data.get("nodetype_schema"), dict)\n    ):\n        return "nodetypes"\n    if data.get("id") == "CW_RULESETS" or (\n        isinstance(data.get("property_rulesets"), list) and isinstance(data.get("link_rulesets"), list)\n    ):\n        return "rulesets"\n    return "other"\n'''
    new_classify = '''def classify(data: Any) -> str:\n    return classify_core_spec(data) or "other"\n'''
    text = replace_once(text, old_classify, new_classify, "classify")

    checker = r'''

def check_core_topology_contract(
    nodetypes: Artifact,
    rulesets: Artifact,
    idx: Indexes,
    ctx: LintContext,
) -> None:
    """Validate the structured One Truth / Many Topologies contract.

    This validates references between already-declared NodeTypes and Link Rulesets;
    it does not create topology semantics in the linter itself.
    """
    model = nodetypes.data.get("core_topology_model")
    links = rulesets.data.get("core_topology_links")
    if not isinstance(model, dict):
        ctx.error("CORE_TOPOLOGY_MODEL_MISSING", nodetypes.path, "$.core_topology_model", "structured core topology model is required")
        return
    if not isinstance(links, dict):
        ctx.error("CORE_TOPOLOGY_LINKS_MISSING", rulesets.path, "$.core_topology_links", "structured core topology link model is required")
        return

    expected_nodetypes = {"topology_entity", "file", "abs", "doc", "ctrct"}
    for nt_ref in sorted(expected_nodetypes):
        if nt_ref not in idx.nodetypes:
            ctx.error("CORE_TOPOLOGY_NODETYPE_UNRESOLVED", nodetypes.path, "$.core_topology_model", f"NodeType {nt_ref!r} does not resolve")

    if model.get("shared_nodetype_ref") != "topology_entity":
        ctx.error("CORE_TOPOLOGY_SHARED_TYPE_INVALID", nodetypes.path, "$.core_topology_model.shared_nodetype_ref", "must resolve topology_entity")
    if model.get("master_implementation_nodetype_ref") != "file":
        ctx.error("CORE_TOPOLOGY_MASTER_INVALID", nodetypes.path, "$.core_topology_model.master_implementation_nodetype_ref", "must resolve file")
    if model.get("type_authority") != "Entity.entity_type_ref":
        ctx.error("CORE_TOPOLOGY_TYPE_AUTHORITY_INVALID", nodetypes.path, "$.core_topology_model.type_authority", "NodeType authority must be Entity.entity_type_ref")
    if model.get("prefix_inference_forbidden") is not True:
        ctx.error("CORE_TOPOLOGY_PREFIX_INFERENCE_INVALID", nodetypes.path, "$.core_topology_model.prefix_inference_forbidden", "prefix inference must be forbidden")

    families = model.get("canonical_identity_families")
    if families != ["#FILE", "#ABS", "#DOC", "#CTRCT"]:
        ctx.error("CORE_TOPOLOGY_FAMILIES_INVALID", nodetypes.path, "$.core_topology_model.canonical_identity_families", "must declare #FILE, #ABS, #DOC, #CTRCT in canonical order")

    serialization = model.get("serialization")
    if not isinstance(serialization, dict):
        ctx.error("CORE_TOPOLOGY_SERIALIZATION_MISSING", nodetypes.path, "$.core_topology_model.serialization", "serialization contract must be structured")
    else:
        for field in ("monolithic_allowed", "sharded_allowed", "semantic_equivalence_required"):
            if serialization.get(field) is not True:
                ctx.error("CORE_TOPOLOGY_SERIALIZATION_INVALID", nodetypes.path, f"$.core_topology_model.serialization.{field}", f"{field} must be true")
        if serialization.get("doc_extension_fixed") is not False:
            ctx.error("CORE_TOPOLOGY_DOC_EXTENSION_INVALID", nodetypes.path, "$.core_topology_model.serialization.doc_extension_fixed", "DOC representation extension must remain open")
        if serialization.get("path_semantic_authority") is not False:
            ctx.error("CORE_TOPOLOGY_PATH_AUTHORITY_INVALID", nodetypes.path, "$.core_topology_model.serialization.path_semantic_authority", "paths must not be semantic authority")

    expected_links = {
        "abstraction_member": ({"file", "abs"}, "abs", "abstraction"),
        "documentation_target": ({"file", "abs"}, "doc", "document"),
        "contract_target": ({"file", "abs"}, "ctrct", "contract"),
    }
    structured_links = links.get("links")
    if not isinstance(structured_links, dict):
        ctx.error("CORE_TOPOLOGY_LINK_MAP_MISSING", rulesets.path, "$.core_topology_links.links", "topology link map must be structured")
        return
    if links.get("closed_link_vocabulary") is not False:
        ctx.error("CORE_TOPOLOGY_LINK_VOCABULARY_CLOSED", rulesets.path, "$.core_topology_links.closed_link_vocabulary", "core Link vocabulary must remain open")

    for link_type, (source_refs, target_ref, owner_role) in expected_links.items():
        decl = structured_links.get(link_type)
        if not isinstance(decl, dict):
            ctx.error("CORE_TOPOLOGY_LINK_DECL_MISSING", rulesets.path, f"$.core_topology_links.links.{link_type}", f"missing structured declaration for {link_type}")
            continue
        if set(decl.get("source_nodetype_refs", [])) != source_refs:
            ctx.error("CORE_TOPOLOGY_LINK_SOURCE_INVALID", rulesets.path, f"$.core_topology_links.links.{link_type}.source_nodetype_refs", f"unexpected source NodeTypes for {link_type}")
        if decl.get("target_nodetype_ref") != target_ref:
            ctx.error("CORE_TOPOLOGY_LINK_TARGET_INVALID", rulesets.path, f"$.core_topology_links.links.{link_type}.target_nodetype_ref", f"unexpected target NodeType for {link_type}")
        if decl.get("owner_role") != owner_role:
            ctx.error("CORE_TOPOLOGY_LINK_OWNER_INVALID", rulesets.path, f"$.core_topology_links.links.{link_type}.owner_role", f"unexpected owner role for {link_type}")

        matching = idx.link_types.get(link_type, [])
        if len(matching) != 1:
            ctx.error("CORE_TOPOLOGY_LINK_RULESET_RESOLUTION", rulesets.path, f"$.core_topology_links.links.{link_type}", f"expected exactly one Link Ruleset for {link_type}, got {len(matching)}")
            continue
        rule = matching[0]
        if rule.get("property_owner") != owner_role:
            ctx.error("CORE_TOPOLOGY_LINK_RULESET_OWNER_MISMATCH", rulesets.path, f"$.link_rulesets[{rule.get('id', link_type)}].property_owner", f"structured owner_role and governing Ruleset disagree for {link_type}")
'''
    text = replace_once(text, '\ndef lint(scan_dir: Path) -> Tuple[LintContext, List[Artifact], Coverage]:\n', checker + '\n\ndef lint(scan_dir: Path) -> Tuple[LintContext, List[Artifact], Coverage]:\n', "topology checker injection")
    text = replace_once(
        text,
        '    idx = build_indexes(nodetypes, rulesets, ctx)\n',
        '    idx = build_indexes(nodetypes, rulesets, ctx)\n    check_core_topology_contract(nodetypes, rulesets, idx, ctx)\n',
        "topology checker call",
    )
    LINTER.write_text(text, encoding="utf-8")


def migrate_validator() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    text = replace_once(text, 'import importlib.util\n', '', "remove importlib.util")
    text = replace_once(text, 'VALIDATOR_VERSION = "1.1.0"', 'VALIDATOR_VERSION = "1.2.0"', "validator version")
    text = replace_once(
        text,
        'from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple\n',
        'from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple\n\ntry:\n    from .cw_spec_common import classify_spec as classify_core_spec\n    from . import cw_spec_lint\nexcept ImportError:  # direct script execution\n    from cw_spec_common import classify_spec as classify_core_spec\n    import cw_spec_lint\n',
        "validator shared imports",
    )
    old_classify = '''def classify_spec(data: Mapping[str, Any]) -> Optional[str]:\n    if data.get("id") == "CANONICAL_CONTRACT_FORMAT" or data.get("type") == "canonical_contract_format":\n        return "ccf"\n    if data.get("id") == "CW_NODETYPES":\n        return "nodetypes"\n    if data.get("id") == "CW_RULESETS":\n        return "rulesets"\n    return None\n'''
    new_classify = '''def classify_spec(data: Mapping[str, Any]) -> Optional[str]:\n    return classify_core_spec(data)\n'''
    text = replace_once(text, old_classify, new_classify, "validator classify")
    old_lint = '''def lint_standard(spec_dir: Path) -> Tuple[bool, str]:\n    """Run the sibling standard self-linter when available."""\n    lint_path = Path(__file__).resolve().with_name("cw_spec_lint.py")\n    if not lint_path.exists():\n        return True, "cw_spec_lint.py not present; standard self-lint skipped"\n    try:\n        spec = importlib.util.spec_from_file_location("cw_spec_lint", lint_path)\n        if spec is None or spec.loader is None:\n            raise RuntimeError("could not import cw_spec_lint.py")\n        module = importlib.util.module_from_spec(spec)\n        sys.modules[spec.name] = module\n        spec.loader.exec_module(module)\n        lint_ctx, _artifacts, _coverage = module.lint(spec_dir)\n        errors = [f for f in lint_ctx.findings if f.severity == "ERROR"]\n        if errors:\n            return False, f"CW standard self-lint failed with {len(errors)} error(s)"\n        return True, "CW standard self-lint passed"\n    except Exception as exc:\n        return False, f"CW standard self-lint could not execute: {exc}"\n'''
    new_lint = '''def lint_standard(spec_dir: Path) -> Tuple[bool, str]:\n    """Run the shared CW specification linter as an imported module."""\n    try:\n        lint_ctx, _artifacts, _coverage = cw_spec_lint.lint(spec_dir)\n        errors = [f for f in lint_ctx.findings if f.severity == "ERROR"]\n        if errors:\n            return False, f"CW standard self-lint failed with {len(errors)} error(s)"\n        return True, "CW standard self-lint passed"\n    except Exception as exc:\n        return False, f"CW standard self-lint could not execute: {exc}"\n'''
    text = replace_once(text, old_lint, new_lint, "validator lint import")
    VALIDATOR.write_text(text, encoding="utf-8")


def migrate_readme() -> None:
    text = README.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    ├── cw_spec_lint.py\n    ├── cw_validate.py\n    └── README.md\n',
        '    ├── __init__.py\n    ├── cw_spec_common.py\n    ├── cw_spec_lint.py\n    ├── cw_validate.py\n    └── README.md\n',
        "readme layout",
    )
    marker = 'Both tools are local-first, use only the Python standard library, and resolve the CW specification directory relative to their own location by default.\n'
    replacement = marker + '\nThe `linter` directory is also an importable Python package. Shared specification discovery/classification lives in `cw_spec_common.py`; executables and external tooling reuse that code rather than maintaining parallel specification-discovery truth. Both direct script execution and package imports are supported.\n'
    text = replace_once(text, marker, replacement, "readme import note")
    README.write_text(text, encoding="utf-8")


def migrate_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '      - name: Compile linter\n        run: python -m py_compile linter/cw_spec_lint.py\n\n      - name: Validate locked CW specification set\n',
        '      - name: Compile CW tooling\n        run: python -m py_compile linter/__init__.py linter/cw_spec_common.py linter/cw_spec_lint.py linter/cw_validate.py\n\n      - name: Verify package imports\n        run: python -c "import linter.cw_spec_common, linter.cw_spec_lint, linter.cw_validate"\n\n      - name: Validate locked CW specification set\n',
        "workflow compile/import",
    )
    WORKFLOW.write_text(text, encoding="utf-8")


def main() -> None:
    migrate_linter()
    migrate_validator()
    migrate_readme()
    migrate_workflow()
    print("CW tooling migration complete")


if __name__ == "__main__":
    main()
