#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .lib.ascii_walk import render_ascii_walk
    from .lib.graph import Edge, Node, collect_graph, load_documents
except ImportError:
    from lib.ascii_walk import render_ascii_walk
    from lib.graph import Edge, Node, collect_graph, load_documents


def render_hierarchy(edges: list[Edge], nodes: dict[str, Node]) -> str:
    return render_ascii_walk(
        edges,
        nodes,
        node_label=lambda ref, mapping: ref if ref in mapping else f"?{ref}",
        edge_label=lambda edge: "",
    )


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
