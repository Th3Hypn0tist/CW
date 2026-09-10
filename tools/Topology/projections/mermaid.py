from __future__ import annotations

import re

from tools.Topology.lib.graph import Edge, Node
from tools.Topology.lib.projection import ProjectionResult


def _mermaid_id(ref: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", ref)
    if not clean:
        clean = "node"
    if clean[0].isdigit():
        clean = f"n_{clean}"
    return clean


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def project(edges: list[Edge], nodes: dict[str, Node]) -> ProjectionResult:
    if not edges:
        return ProjectionResult(
            name="mermaid",
            lines=("flowchart TD", "%% no matching links"),
            markdown_fence="mermaid",
        )

    refs = sorted(
        {edge.parent_ref for edge in edges} | {edge.child_ref for edge in edges}
    )
    ids = {ref: _mermaid_id(ref) for ref in refs}

    lines: list[str] = ["flowchart TD"]
    for ref in refs:
        node = nodes.get(ref)
        label = node.name if node is not None and node.name else ref
        if ref not in nodes:
            label = f"?{ref}"
        lines.append(f'    {ids[ref]}["{_escape_label(label)}"]')

    for edge in sorted(edges, key=lambda item: (item.relation, item.parent_ref, item.child_ref, item.link_ref)):
        relation = _escape_label(edge.relation)
        lines.append(
            f'    {ids[edge.parent_ref]} -->|"{relation}"| {ids[edge.child_ref]}'
        )

    return ProjectionResult(
        name="mermaid",
        lines=tuple(lines),
        markdown_fence="mermaid",
    )
