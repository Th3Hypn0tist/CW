import json
from pathlib import Path

from tools.Topology.lib.graph import collect_graph, collect_structure_tree, load_documents
from tools.Topology.lib.projector import TopologyProjector


def _model() -> dict:
    return {
        "format": {"contract_format": "CANONICAL_CONTRACT", "format_version": "2.1"},
        "identity": {"id": "TEST", "name": "TEST", "type": "test", "version": "0.0.0"},
        "entities": [
            {
                "id": "#FILE:system:parser",
                "name": "parser",
                "entity_type_ref": "code",
                "status": "unlocked",
                "properties": [
                    {
                        "id": "LINK::test",
                        "name": "test",
                        "property_type_ref": "link",
                        "ruleset_ref": "RULESET_LINK",
                        "status": "unlocked",
                        "value": {
                            "link_type_ref": "dependency",
                            "parent_ref": "#FILE:system:parser",
                            "child_ref": "#FILE:system:target",
                        },
                    }
                ],
            },
            {
                "id": "#FILE:system:target",
                "name": "target",
                "entity_type_ref": "code",
                "status": "unlocked",
                "properties": [],
            },
        ],
    }


def _assert_monotonic(values: list[float | int]) -> None:
    assert values
    assert values == sorted(values)


def test_load_documents_reports_real_artifact_progress(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    path.write_text(json.dumps(_model()), encoding="utf-8")
    updates: list[tuple[float, str]] = []

    documents = load_documents(path, progress=lambda value, detail: updates.append((value, detail)))

    assert documents
    values = [value for value, _ in updates]
    _assert_monotonic(values)
    assert values[0] == 0.0
    assert values[-1] == 1.0
    assert any("reading 1/1" in detail for _, detail in updates)


def test_graph_builders_report_progress() -> None:
    documents = [(Path("model.json"), _model())]
    graph_updates: list[tuple[float, str]] = []
    tree_updates: list[tuple[float, str]] = []

    collect_graph(documents, progress=lambda value, detail: graph_updates.append((value, detail)))
    collect_structure_tree(documents, progress=lambda value, detail: tree_updates.append((value, detail)))

    for updates in (graph_updates, tree_updates):
        values = [value for value, _ in updates]
        _assert_monotonic(values)
        assert values[0] == 0.0
        assert values[-1] == 1.0


def test_projector_open_maps_pipeline_to_zero_through_100(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    path.write_text(json.dumps(_model()), encoding="utf-8")
    updates: list[tuple[int, str]] = []

    projector = TopologyProjector()
    projector.open(path, progress=lambda value, detail: updates.append((value, detail)))

    values = [value for value, _ in updates]
    _assert_monotonic(values)
    assert values[0] == 0
    assert values[-1] == 100
    assert any("canonical graph" in detail for _, detail in updates)
    assert any("StructureTree" in detail for _, detail in updates)
    assert updates[-1][1] == "CW ready"
