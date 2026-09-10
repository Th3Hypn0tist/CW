from __future__ import annotations

import curses
from dataclasses import dataclass
from pathlib import Path

from tools.Topology.lib.ascii_walk import render_ascii_walk
from tools.Topology.lib.curses_view import CursesViewHost
from tools.Topology.lib.graph import Edge, Node, collect_graph, load_documents


@dataclass
class TopologyState:
    source: Path
    topology: str = "containment"
    mode: str = "hierarchy"


class TopologyView:
    def __init__(self, source: Path) -> None:
        self.state = TopologyState(source=source.resolve())
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.relations: list[str] = []
        self.reload()

    def reload(self) -> None:
        documents = load_documents(self.state.source)
        self.nodes, self.edges = collect_graph(documents)
        self.relations = sorted({edge.relation for edge in self.edges})
        if self.relations and self.state.topology not in self.relations:
            self.state.topology = self.relations[0]

    def lines(self) -> list[str]:
        selected = [edge for edge in self.edges if edge.relation == self.state.topology]
        if not selected:
            return ["(no matching links)"]

        text = render_ascii_walk(
            selected,
            self.nodes,
            node_label=lambda ref, mapping: ref if ref in mapping else f"?{ref}",
            edge_label=(
                (lambda edge: "")
                if self.state.mode == "hierarchy"
                else (lambda edge: edge.relation)
            ),
        )
        return text.splitlines()

    def status(self) -> str:
        return (
            f"source={self.state.source}  "
            f"topology={self.state.topology}  "
            f"view={self.state.mode}"
        )

    def export_markdown(self, path: Path) -> None:
        body = "\n".join(self.lines())
        text = (
            f"# CW Topology\n\n"
            f"- Source: `{self.state.source}`\n"
            f"- Topology: `{self.state.topology}`\n"
            f"- View: `{self.state.mode}`\n\n"
            f"```text\n{body}\n```\n"
        )
        path.write_text(text, encoding="utf-8")


def run(source: Path) -> None:
    view = TopologyView(source)

    def app(stdscr: curses.window) -> None:
        host = CursesViewHost(
            title="CW Topology",
            render_lines=view.lines,
            status_line=view.status,
            footer="up/down scroll  o open  t topology/view  e export .md  q q q quit",
        )

        def open_dialog(current: CursesViewHost) -> None:
            value = current.prompt(stdscr, "Open CW source", str(view.state.source))
            if value is None or not value:
                return
            try:
                view.state.source = Path(value).expanduser().resolve()
                view.reload()
                current.scroll = 0
                current.message = "source opened"
            except Exception as exc:
                current.message = f"open failed: {exc}"

        def topology_dialog(current: CursesViewHost) -> None:
            options = [f"topology: {relation}" for relation in view.relations]
            options.extend(["view: hierarchy", "view: topology"])
            if not options:
                current.message = "no topology types available"
                return

            selected = current.choose(stdscr, "Topology / View", options)
            if selected is None:
                return
            choice = options[selected]
            if choice.startswith("topology: "):
                view.state.topology = choice.split(": ", 1)[1]
            elif choice == "view: hierarchy":
                view.state.mode = "hierarchy"
            elif choice == "view: topology":
                view.state.mode = "topology"
            current.scroll = 0
            current.message = choice

        def export_dialog(current: CursesViewHost) -> None:
            default = f"{view.state.source.stem}_{view.state.topology}.md"
            value = current.prompt(stdscr, "Export Markdown", default)
            if value is None or not value:
                return
            path = Path(value).expanduser()
            if path.suffix.lower() != ".md":
                path = path.with_suffix(".md")
            try:
                view.export_markdown(path)
                current.message = f"exported: {path}"
            except Exception as exc:
                current.message = f"export failed: {exc}"

        host.key_handlers.update({"o": open_dialog, "t": topology_dialog, "e": export_dialog})
        host.run(stdscr)

    curses.wrapper(app)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Interactive CW topology View")
    parser.add_argument("source", type=Path, help="Canonical CW artifact or folder")
    args = parser.parse_args()

    try:
        run(args.source)
    except Exception as exc:
        print(f"cw-topology-tui: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
