#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

try:
    from .cw_topology import Edge, Node, collect_graph, load_documents, roots_for
except ImportError:
    from cw_topology import Edge, Node, collect_graph, load_documents, roots_for


def render_hierarchy(edges: list[Edge], nodes: dict[str, Node]) -> str:
    if not edges:
        return "(no matching links)"

    outgoing: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.parent_ref].append(edge)
    for children in outgoing.values():
        children.sort(key=lambda edge: (edge.child_ref, edge.link_ref))

    rendered: set[str] = set()
    lines: list[str] = []

    def label(ref: str) -> str:
        return ref if ref in nodes else f"?{ref}"

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

            lines.append(f"{prefix}{branch}{label(child)}{suffix}")
            rendered.add(child)

            if not suffix and child in outgoing:
                walk(child, prefix + continuation, stack + (child,))

    all_refs = sorted(
        {edge.parent_ref for edge in edges} | {edge.child_ref for edge in edges}
    )
    roots = roots_for(edges)
    root_order = roots + [ref for ref in all_refs if ref not in roots]

    for root in root_order:
        if root in rendered:
            continue
        if lines:
            lines.append("")
        lines.append(label(root))
        rendered.add(root)
        walk(root, "", (root,))

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print one explicit CW Link relation as a plain ASCII hierarchy."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Canonical .json/.cw artifact or sharded CW folder",
    )
    parser.add_argument(
        "topology",
        help="Exact canonical value.link_type_ref to render",
    )
    args = parser.parse_args()

    try:
        documents = load_documents(args.input.resolve())
        nodes, edges = collect_graph(documents)
    except Exception as exc:
        print(f"cw-hierarchy: {exc}", file=sys.stderr)
        return 2

    selected = [edge for edge in edges if edge.relation == args.topology]
    if not selected:
        print(f"cw-hierarchy: topology not present: {args.topology}", file=sys.stderr)
        return 1

    print(render_hierarchy(selected, nodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
