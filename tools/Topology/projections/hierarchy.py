from __future__ import annotations

from tools.Topology.lib.ascii_walk import render_ascii_walk
from tools.Topology.lib.graph import (
    STRUCTURE_DIR_PREFIX,
    STRUCTURE_ROOT_REF,
    Edge,
    Node,
)
from tools.Topology.lib.projection import ProjectionResult


def _label(ref: str, nodes: dict[str, Node]) -> str:
    node = nodes.get(ref)
    if ref == STRUCTURE_ROOT_REF or ref.startswith(STRUCTURE_DIR_PREFIX):
        if node is not None and node.name:
            return node.name
    return ref


def project(edges: list[Edge], nodes: dict[str, Node]) -> ProjectionResult:
    if not edges:
        return ProjectionResult(name="hierarchy", lines=("ROOT",))

    text = render_ascii_walk(
        edges,
        nodes,
        node_label=_label,
        edge_label=lambda edge: "",
    )
    return ProjectionResult(name="hierarchy", lines=tuple(text.splitlines()))
