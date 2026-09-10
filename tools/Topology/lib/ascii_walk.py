from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Mapping, Sequence


def roots_for(edges: Sequence[Any]) -> list[str]:
    parents = {edge.parent_ref for edge in edges}
    children = {edge.child_ref for edge in edges}
    return sorted(parents - children)


def render_ascii_walk(
    edges: Sequence[Any],
    nodes: Mapping[str, Any],
    *,
    node_label: Callable[[str, Mapping[str, Any]], str],
    edge_label: Callable[[Any], str],
) -> str:
    if not edges:
        return "(no matching links)"

    outgoing: dict[str, list[Any]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.parent_ref].append(edge)
    for edge_list in outgoing.values():
        edge_list.sort(
            key=lambda edge: (edge.relation, edge.child_ref, edge.link_ref)
        )

    rendered: set[str] = set()
    lines: list[str] = []

    def walk(ref: str, prefix: str, stack: tuple[str, ...]) -> None:
        children = outgoing.get(ref, [])
        for index, edge in enumerate(children):
            last = index == len(children) - 1
            branch = "`-- " if last else "|-- "
            continuation = "    " if last else "|   "
            child = edge.child_ref

            suffix = ""
            if child in stack:
                suffix = " [cycle]"
            elif child in rendered:
                suffix = " [seen]"
            elif child not in nodes:
                suffix = " [unresolved]"

            label = edge_label(edge)
            edge_prefix = f"{label} --> " if label else ""
            lines.append(
                f"{prefix}{branch}{edge_prefix}{node_label(child, nodes)}{suffix}"
            )
            rendered.add(child)

            if not suffix and outgoing.get(child):
                walk(child, prefix + continuation, stack + (child,))

    all_refs = sorted(
        {edge.parent_ref for edge in edges} | {edge.child_ref for edge in edges}
    )
    roots = roots_for(edges)
    root_set = set(roots)
    root_order = roots + [ref for ref in all_refs if ref not in root_set]

    for root in root_order:
        if root in rendered:
            continue
        if lines:
            lines.append("")
        if root not in root_set:
            lines.append("[no root]")
        lines.append(node_label(root, nodes))
        rendered.add(root)
        walk(root, "", (root,))

    return "\n".join(lines)
