from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "linter" / "cw_compose.py").is_file() and (
            parent / "linter" / "cw_spec_common.py"
        ).is_file():
            return parent
    raise RuntimeError("CW repository root not found")


REPO_ROOT = find_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from linter.cw_compose import compose_documents
from linter.cw_spec_common import read_json


@dataclass(frozen=True)
class Node:
    ref: str
    name: str | None


@dataclass(frozen=True)
class Edge:
    link_ref: str
    relation: str
    parent_ref: str
    child_ref: str


def artifact_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise FileNotFoundError(root)
    paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".cw", ".json"}
    ]
    return sorted(paths, key=lambda path: (path.as_posix().casefold(), path.as_posix()))


def load_documents(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return compose_documents(artifact_paths(root), read_json)


def collect_graph(
    documents: Iterable[tuple[Path, dict[str, Any]]],
) -> tuple[dict[str, Node], list[Edge]]:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    for _, document in documents:
        entities = document.get("entities")
        if not isinstance(entities, list):
            continue

        for entity in entities:
            if not isinstance(entity, dict):
                continue

            entity_ref = entity.get("id")
            if isinstance(entity_ref, str) and entity_ref:
                name = entity.get("name")
                nodes[entity_ref] = Node(
                    ref=entity_ref,
                    name=name if isinstance(name, str) and name else None,
                )

            properties = entity.get("properties")
            if not isinstance(properties, list):
                continue

            for prop in properties:
                if not isinstance(prop, dict):
                    continue

                prop_ref = prop.get("id")
                if isinstance(prop_ref, str) and prop_ref:
                    prop_name = prop.get("name")
                    nodes[prop_ref] = Node(
                        ref=prop_ref,
                        name=prop_name if isinstance(prop_name, str) and prop_name else None,
                    )

                if prop.get("property_type_ref") != "link":
                    continue

                value = prop.get("value")
                if not isinstance(value, dict):
                    continue

                relation = value.get("link_type_ref")
                parent_ref = value.get("parent_ref")
                child_ref = value.get("child_ref")

                if not all(
                    isinstance(item, str) and item
                    for item in (prop_ref, relation, parent_ref, child_ref)
                ):
                    continue

                edges.append(
                    Edge(
                        link_ref=prop_ref,
                        relation=relation,
                        parent_ref=parent_ref,
                        child_ref=child_ref,
                    )
                )

    edges.sort(key=lambda edge: (edge.relation, edge.parent_ref, edge.child_ref, edge.link_ref))
    return nodes, edges
