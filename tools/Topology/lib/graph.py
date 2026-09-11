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


STRUCTURE_ROOT_REF = "@STRUCTURETREE:ROOT"
STRUCTURE_DIR_PREFIX = "@STRUCTURETREE:DIR:"


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


def _structure_address(entity_ref: str) -> tuple[str, ...]:
    """Return projection-only directory nodes from an explicit canonical Node id.

    Identity-family prefixes are used only as already-present StructureTree
    navigation addresses. They never infer or replace Entity.entity_type_ref.
    """
    if not entity_ref.startswith("#"):
        return ()

    parts = tuple(entity_ref.split(":"))
    if len(parts) < 2 or any(not part for part in parts):
        return ()

    # The final identity component is represented by the canonical Entity leaf.
    # Everything before it is the navigation hierarchy under the common ROOT.
    return parts[:-1]


def _structure_dir_ref(parts: tuple[str, ...]) -> str:
    return STRUCTURE_DIR_PREFIX + ":".join(parts)


def collect_structure_tree(
    documents: Iterable[tuple[Path, dict[str, Any]]],
) -> tuple[dict[str, Node], list[Edge]]:
    """Build one projection-only StructureTree over all canonical Entity Nodes.

    Directory nodes and directory_child edges exist only in this derived
    navigation graph. They never become canonical Entities or Link Properties.
    """
    nodes: dict[str, Node] = {
        STRUCTURE_ROOT_REF: Node(ref=STRUCTURE_ROOT_REF, name="ROOT")
    }
    edges: list[Edge] = []
    linked_directories: set[tuple[str, str]] = set()
    linked_entities: set[tuple[str, str]] = set()

    for _, document in documents:
        entities = document.get("entities")
        if not isinstance(entities, list):
            continue

        for entity in entities:
            if not isinstance(entity, dict):
                continue

            entity_ref = entity.get("id")
            if not isinstance(entity_ref, str) or not entity_ref:
                continue

            name = entity.get("name")
            nodes[entity_ref] = Node(
                ref=entity_ref,
                name=name if isinstance(name, str) and name else None,
            )

            parent_ref = STRUCTURE_ROOT_REF
            address_parts: list[str] = []

            for label in _structure_address(entity_ref):
                address_parts.append(label)
                directory_ref = _structure_dir_ref(tuple(address_parts))
                nodes.setdefault(
                    directory_ref,
                    Node(ref=directory_ref, name=label),
                )

                key = (parent_ref, directory_ref)
                if key not in linked_directories:
                    edges.append(
                        Edge(
                            link_ref=f"@STRUCTURETREE:EDGE:{len(edges):08d}",
                            relation="directory_child",
                            parent_ref=parent_ref,
                            child_ref=directory_ref,
                        )
                    )
                    linked_directories.add(key)

                parent_ref = directory_ref

            key = (parent_ref, entity_ref)
            if key not in linked_entities:
                edges.append(
                    Edge(
                        link_ref=f"@STRUCTURETREE:EDGE:{len(edges):08d}",
                        relation="directory_child",
                        parent_ref=parent_ref,
                        child_ref=entity_ref,
                    )
                )
                linked_entities.add(key)

    edges.sort(key=lambda edge: (edge.parent_ref, edge.child_ref, edge.link_ref))
    return nodes, edges
