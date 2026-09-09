from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from linter.cw_spec_common import resolve_bundle
from linter.cw_version import calculate_entity_hash

ROOT = Path(__file__).resolve().parents[2]
SPEC_SET = ROOT / "spec_sets" / "CW_CORE_v1.1.0.json"
VALIDATOR = ROOT / "linter" / "cw_validate.py"


def _entity(ref: str, nodetype: str, *, members=None) -> dict:
    value = {
        "id": ref,
        "name": ref.rsplit(":", 1)[-1],
        "entity_type_ref": nodetype,
        "status": "unlocked",
        "properties": [],
    }
    if nodetype == "code":
        value["required_links"] = []
    if members is not None:
        value["members"] = members
    return value


def _link(prop_id: str, relation: str, parent: str, child: str, ruleset: str = "RULESET_LINK") -> dict:
    return {
        "id": prop_id,
        "property_type_ref": "link",
        "ruleset_ref": ruleset,
        "status": "unlocked",
        "value": {
            "link_type_ref": relation,
            "parent_ref": parent,
            "child_ref": child,
            "properties": {},
        },
    }


def _document() -> dict:
    topology = _entity("#ABS:Runtime", "abs")
    file_a = _entity("#FILE:a", "code")
    file_b = _entity("#FILE:b", "code")
    contract = _entity("#CTRCT:Parser", "contract", members=["#FILE:a"])
    topology["properties"].append(_link("LINK::ABS_RUNTIME", "#ABS:Runtime", "#FILE:a", "#FILE:b"))
    file_b["properties"].append(
        _link(
            "LINK::B_PARSER_CONTRACT",
            "contract_affiliation",
            "#FILE:b",
            "#CTRCT:Parser",
            "RULESET_LINK_CONTRACT_AFFILIATION",
        )
    )
    return {
        "format": {"contract_format": "CANONICAL_CONTRACT", "format_version": "2.1"},
        "identity": {"id": "CW_CORE_1_1_TEST", "name": "CW Core 1.1 Test", "type": "test", "version": "1.0.0"},
        "specification_ref": "CW_CORE@1.1.0",
        "status": "unlocked",
        "purpose": "CW Core 1.1 regression fixture",
        "scope": {"owns": ["test model"], "does_not_own": []},
        "entities": [topology, file_a, file_b, contract],
        "constraints": {"invariants": []},
        "references": [],
        "gaps": [],
        "prose": {"summary": "test", "notes": []},
    }


def _add_required_dependency(document: dict, *, endpoint_nodetype: str) -> None:
    file_a = document["entities"][1]
    file_b = document["entities"][2]
    file_a["required_links"] = [
        {
            "id": "REQ_DEP",
            "link_type_ref": "dependency",
            "self_endpoint": "child_ref",
            "min": 1,
            "other_endpoint": {"entity_nodetype_ref": endpoint_nodetype},
        }
    ]
    link = _link("LINK::B_TO_A", "dependency", "#FILE:b", "#FILE:a", "RULESET_LINK_DEPENDENCY")
    link["value"]["required_link_ref"] = {"entity_ref": "#FILE:a", "required_link_id": "REQ_DEP"}
    file_b["properties"].append(link)


def _run(document: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "model.json"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), str(path), "--spec-set", str(SPEC_SET), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if not completed.stdout.strip():
            raise AssertionError(completed.stderr)
        return json.loads(completed.stdout)


class CWCore11Tests(unittest.TestCase):
    def test_default_bundle_is_locked_core_1_1(self) -> None:
        bundle = resolve_bundle(default_start=ROOT / "linter")
        self.assertEqual(bundle.ccf.get("version"), "2.4.3")
        self.assertEqual(bundle.nodetypes.get("version"), "1.18.0")
        self.assertEqual(bundle.rulesets.get("version"), "3.14.0")

    def test_topology_members_and_contract_affiliation_are_ready(self) -> None:
        result = _run(_document())
        self.assertEqual(result["result"], "READY", result)

    def test_literal_relation_does_not_resolve_as_topology_identity(self) -> None:
        document = _document()
        document["entities"][0]["properties"][0]["value"]["link_type_ref"] = "ABS:Runtime:dependency"
        result = _run(document)
        self.assertEqual(result["result"], "READY", result)
        self.assertFalse(any(item["code"].startswith("LINK_TOPOLOGY") for item in result["findings"]))

    def test_missing_topology_identity_is_unready(self) -> None:
        document = _document()
        document["entities"][0]["properties"][0]["value"]["link_type_ref"] = "#ABS:Missing"
        result = _run(document)
        self.assertEqual(result["result"], "UNREADY", result)
        self.assertTrue(any(item["code"] == "LINK_TOPOLOGY_REF_UNRESOLVED" for item in result["findings"]))

    def test_duplicate_contract_member_is_invalid(self) -> None:
        document = _document()
        document["entities"][3]["members"] = ["#FILE:a", "#FILE:a"]
        result = _run(document)
        self.assertEqual(result["result"], "INVALID_MODEL", result)
        self.assertTrue(any(item["code"] == "NODE_SECTION_REF_DUPLICATE" for item in result["findings"]))

    def test_required_link_other_endpoint_accepts_matching_nodetype(self) -> None:
        document = _document()
        _add_required_dependency(document, endpoint_nodetype="code")
        result = _run(document)
        self.assertEqual(result["result"], "READY", result)
        self.assertFalse(any(item["code"] == "REQUIRED_LINK_UNSATISFIED" for item in result["findings"]))

    def test_required_link_bound_to_wrong_other_endpoint_is_invalid(self) -> None:
        document = _document()
        _add_required_dependency(document, endpoint_nodetype="contract")
        result = _run(document)
        self.assertEqual(result["result"], "INVALID_MODEL", result)
        self.assertTrue(any(item["code"] == "REQUIRED_LINK_BINDING_INCOMPATIBLE" for item in result["findings"]))

    def test_tampered_node_version_is_invalid(self) -> None:
        document = _document()
        entity = document["entities"][1]
        entity["timestamp"] = "20260909143000"
        entity["hash"] = ""
        entity["hash"] = calculate_entity_hash(entity)
        entity["name"] = "tampered"
        result = _run(document)
        self.assertEqual(result["result"], "INVALID_MODEL", result)
        self.assertTrue(any(item["code"] == "NODE_VERSION_INVALID" for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
