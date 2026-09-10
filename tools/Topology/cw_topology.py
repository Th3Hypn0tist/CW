#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    from .lib.ascii_walk import render_ascii_walk
    from .lib.graph import Edge, Node, collect_graph, load_documents
except ImportError:
    from lib.ascii_walk import render_ascii_walk
    from lib.graph import Edge, Node, collect_graph, load_documents


def display_ref(ref: str, nodes: dict[str, Node], show_names: bool) -> str:
    node = nodes.get(ref)
    if node is None:
        return f"?{ref}"
    if show_names and node.name and node.name != ref:
        return f"{ref} ({node.name})"
    return ref


def edge_label(edge: Edge, show_link_ids: bool) -> str:
    if show_link_ids:
        return f"{edge.relation} [{edge.link_ref}]"
    return edge.relation


def select_edges(edges: list[Edge], relations: set[str] | None) -> list[Edge]:
    if relations is None:
        return list(edges)
    return [edge for edge in edges if edge.relation in relations]


def relation_counts(edges: list[Edge]) -> list[tuple[str, int]]:
    counts = Counter(edge.relation for edge in edges)
    return sorted(counts.items(), key=lambda item: item[0])


def render_ascii(
    edges: list[Edge],
    nodes: dict[str, Node],
    *,
    show_names: bool = False,
    show_link_ids: bool = False,
) -> str:
    return render_ascii_walk(
        edges,
        nodes,
        node_label=lambda ref, mapping: display_ref(ref, mapping, show_names),
        edge_label=lambda edge: edge_label(edge, show_link_ids),
    )


def parse_relations(values: list[str]) -> set[str]:
    relations: set[str] = set()
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                relations.add(item)
    return relations


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print explicit canonical CW Link topologies as deterministic ASCII. "
            "No topology or relation semantics are inferred from names, paths, "
            "filenames, geometry, or rendering."
        )
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Canonical .json/.cw artifact or sharded CW folder",
    )
    parser.add_argument(
        "-r",
        "--relation",
        "-t",
        "--topology",
        action="append",
        default=[],
        help=(
            "Explicit value.link_type_ref to include. Repeat or comma-separate. "
            "If omitted, all explicit Links are rendered together."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List explicit relation selectors present in the artifact and exit",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print one separate ASCII topology for every explicit relation selector",
    )
    parser.add_argument(
        "--link-ids",
        action="store_true",
        help="Include canonical Link Property ids in edge labels",
    )
    parser.add_argument(
        "--names",
        action="store_true",
        help="Append explicit Node names when available; canonical ids remain primary",
    )
    args = parser.parse_args()

    try:
        documents = load_documents(args.input.resolve())
        nodes, edges = collect_graph(documents)
    except Exception as exc:
        print(f"cw-topology: {exc}", file=sys.stderr)
        return 2

    counts = relation_counts(edges)

    if args.list:
        if not counts:
            print("(no explicit canonical Links)")
            return 0
        width = max(len(relation) for relation, _ in counts)
        for relation, count in counts:
            print(f"{relation:<{width}}  {count}")
        return 0

    requested = parse_relations(args.relation)

    if args.all:
        for index, (relation, count) in enumerate(counts):
            if index:
                print()
            print(f"== {relation} ({count}) ==")
            print(
                render_ascii(
                    select_edges(edges, {relation}),
                    nodes,
                    show_names=args.names,
                    show_link_ids=args.link_ids,
                )
            )
        return 0

    selected = select_edges(edges, requested if requested else None)
    if requested:
        available = {relation for relation, _ in counts}
        missing = sorted(requested - available)
        if missing:
            print(
                "cw-topology: relation(s) not present: " + ", ".join(missing),
                file=sys.stderr,
            )
            return 1
        print("== " + ", ".join(sorted(requested)) + " ==")
    else:
        print("== all explicit Links ==")

    print(
        render_ascii(
            selected,
            nodes,
            show_names=args.names,
            show_link_ids=args.link_ids,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
