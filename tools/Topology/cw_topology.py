#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
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
    kind: str
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
                    kind="Entity",
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
                        kind="Property",
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


def roots_for(edges: list[Edge]) -> list[str]:
    parents = {edge.parent_ref for edge in edges}
    children = {edge.child_ref for edge in edges}
    roots = sorted(parents - children)
    if roots:
        return roots
    return [min(parents | children)] if parents or children else []


def render_ascii(
    edges: list[Edge],
    nodes: dict[str, Node],
    *,
    show_names: bool = False,
    show_link_ids: bool = False,
) -> str:
    if not edges:
        return "(no matching links)"

    outgoing: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.parent_ref].append(edge)
    for edge_list in outgoing.values():
        edge_list.sort(key=lambda edge: (edge.relation, edge.child_ref, edge.link_ref))

    rendered_nodes: set[str] = set()
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
            elif child in rendered_nodes:
                suffix = " [seen]"
            elif child not in nodes:
                suffix = " [unresolved]"

            lines.append(
                f"{prefix}{branch}{edge_label(edge, show_link_ids)} --> "
                f"{display_ref(child, nodes, show_names)}{suffix}"
            )
            rendered_nodes.add(child)

            if not suffix and outgoing.get(child):
                walk(child, prefix + continuation, stack + (child,))

    all_refs = sorted(
        {edge.parent_ref for edge in edges} | {edge.child_ref for edge in edges}
    )
    roots = roots_for(edges)
    root_order = roots + [ref for ref in all_refs if ref not in roots]

    printed_roots: set[str] = set()
    for root in root_order:
        if root in printed_roots or root in rendered_nodes:
            continue
        if lines:
            lines.append("")
        lines.append(display_ref(root, nodes, show_names))
        printed_roots.add(root)
        rendered_nodes.add(root)
        walk(root, "", (root,))

    return "\n".join(lines)


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
