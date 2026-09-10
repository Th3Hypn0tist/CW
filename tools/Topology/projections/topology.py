from __future__ import annotations

from tools.Topology.lib.ascii_walk import render_ascii_walk
from tools.Topology.lib.graph import Edge, Node
from tools.Topology.lib.projection import ProjectionResult


def project(edges: list[Edge], nodes: dict[str, Node]) -> ProjectionResult:
    text = render_ascii_walk(
        edges,
        nodes,
        node_label=lambda ref, mapping: ref if ref in mapping else f"?{ref}",
        edge_label=lambda edge: edge.relation,
    )
    return ProjectionResult(name="topology", lines=tuple(text.splitlines()))
