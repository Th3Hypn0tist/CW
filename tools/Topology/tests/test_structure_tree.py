from pathlib import Path

from tools.Topology.lib.graph import collect_structure_tree
from tools.Topology.projections.hierarchy import project


def _document() -> dict:
    return {
        "entities": [
            {
                "id": "#FILE:system:commands:parser",
                "name": "parser",
                "entity_type_ref": "code",
                "status": "unlocked",
                "properties": [],
            },
            {
                "id": "#FILE:system:commands:registry",
                "name": "registry",
                "entity_type_ref": "code",
                "status": "unlocked",
                "properties": [],
            },
            {
                "id": "#DOC:runtime:overview",
                "name": "overview",
                "entity_type_ref": "doc",
                "status": "unlocked",
                "properties": [],
            },
            {
                "id": "#CTRCT:Runtime:commands:00_Command_Surface_Parser",
                "name": "contract",
                "entity_type_ref": "contract",
                "status": "unlocked",
                "properties": [],
            },
            {
                "id": "#ABS:Runtime:CommandSurface",
                "name": "abs",
                "entity_type_ref": "abs",
                "status": "unlocked",
                "properties": [],
            },
        ]
    }


def test_all_identity_families_share_one_root() -> None:
    nodes, edges = collect_structure_tree([(Path("CW/model.cw"), _document())])
    text = project(edges, nodes).text

    assert text.splitlines()[0] == "ROOT"
    for branch in ("#FILE", "#DOC", "#CTRCT", "#ABS"):
        assert branch in text


def test_directory_nodes_are_projection_only_and_entities_remain_leaves() -> None:
    nodes, edges = collect_structure_tree([(Path("CW/model.cw"), _document())])
    text = project(edges, nodes).text

    assert "system" in text
    assert "commands" in text
    assert "#FILE:system:commands:parser" in text
    assert all(edge.relation == "directory_child" for edge in edges)


def test_non_family_entity_is_not_dropped() -> None:
    document = {
        "entities": [
            {
                "id": "ROOT_SERVICE",
                "name": "service",
                "entity_type_ref": "component",
                "status": "unlocked",
                "properties": [],
            }
        ]
    }
    nodes, edges = collect_structure_tree([(Path("model.json"), document)])
    assert project(edges, nodes).text == "ROOT\n`-- ROOT_SERVICE"
