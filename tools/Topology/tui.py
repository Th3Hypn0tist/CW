from __future__ import annotations

import curses
from pathlib import Path

from tools.CodeImport.cw_export import export_cw
from tools.CodeImport.importer import CodeImporter
from tools.Topology.lib.curses_view import CursesViewHost
from tools.Topology.lib.projector import TopologyProjector


def run(source: Path | None = None) -> None:
    projector = TopologyProjector(source)
    code_importer = CodeImporter()

    def render_lines() -> list[str]:
        return list(projector.project().lines)

    def status() -> str:
        source_text = str(projector.state.source) if projector.state.source else "<none>"
        return (
            f"source={source_text}  "
            f"topology={projector.state.topology}  "
            f"projection={projector.state.projection}"
        )

    def app(stdscr: curses.window) -> None:
        host = CursesViewHost(
            title="CW Topology",
            render_lines=render_lines,
            status_line=status,
            footer=(
                "up/down scroll  o open CW  c code import  t topology  "
                "h hierarchy/view  e export .md  q q q quit"
            ),
        )

        def open_dialog(current: CursesViewHost) -> None:
            start = projector.state.source or Path.cwd()
            selected = current.browse_path(
                stdscr,
                "Open CW source",
                start=start,
                file_filter=lambda path: path.suffix.lower() in {".cw", ".json"},
                allow_directories=True,
            )
            if selected is None:
                return
            try:
                projector.open(selected)
                current.scroll = 0
                current.message = f"source opened: {selected}"
            except Exception as exc:
                current.message = f"open failed: {exc}"

        def code_import_dialog(current: CursesViewHost) -> None:
            selected = current.browse_path(
                stdscr,
                "Code import source",
                start=Path.cwd(),
                file_filter=None,
                allow_directories=True,
            )
            if selected is None:
                return

            try:
                imported = code_importer.import_source(selected)
            except Exception as exc:
                current.message = f"code import failed: {exc}"
                return

            if not imported.nodes:
                parser_ids = ", ".join(code_importer.registry.ids()) or "<none>"
                current.message = (
                    f"no supported code found in {selected}  parsers={parser_ids}"
                )
                return

            if selected.is_dir():
                default_dir = selected.parent
                default_name = f"{selected.name}.cw"
            else:
                default_dir = selected.parent
                default_name = f"{selected.stem}.cw"

            destination_text = current.prompt(
                stdscr,
                "Export imported code to CW",
                str(default_dir / default_name),
            )
            if destination_text is None or not destination_text:
                current.message = "code import cancelled before CW export"
                return

            destination = Path(destination_text).expanduser()
            if destination.suffix.lower() not in {".cw", ".json"}:
                destination = destination.with_suffix(".cw")

            try:
                exported = export_cw(imported, destination)
                projector.open(exported)
                current.scroll = 0
                current.message = (
                    f"code imported -> {exported}  "
                    f"nodes={len(imported.nodes)} edges={len(imported.edges)} "
                    f"findings={len(imported.findings)}"
                )
            except Exception as exc:
                current.message = f"CW export/open failed: {exc}"

        def topology_dialog(current: CursesViewHost) -> None:
            options = list(projector.relations)
            if not options:
                current.message = "no topology types available"
                return

            try:
                selected_index = options.index(projector.state.topology)
            except ValueError:
                selected_index = 0

            selected = current.choose(
                stdscr,
                "Topology",
                options,
                selected=selected_index,
            )
            if selected is None:
                return

            projector.select_topology(options[selected])
            current.scroll = 0
            current.message = f"topology: {projector.state.topology}"

        def hierarchy_dialog(current: CursesViewHost) -> None:
            options = list(projector.projections)
            if not options:
                current.message = "no projections available"
                return

            try:
                selected_index = options.index(projector.state.projection)
            except ValueError:
                selected_index = 0

            selected = current.choose(
                stdscr,
                "Hierarchy / View",
                options,
                selected=selected_index,
            )
            if selected is None:
                return

            projector.select_projection(options[selected])
            current.scroll = 0
            current.message = f"projection: {projector.state.projection}"

        def export_dialog(current: CursesViewHost) -> None:
            if projector.state.source is None:
                current.message = "no source loaded"
                return

            result = projector.project()
            default = (
                f"{projector.state.source.stem}_"
                f"{projector.state.topology}_"
                f"{projector.state.projection}.md"
            )
            value = current.prompt(stdscr, "Export Markdown", default)
            if value is None or not value:
                return

            path = Path(value).expanduser()
            if path.suffix.lower() != ".md":
                path = path.with_suffix(".md")

            text = (
                "# CW Topology\n\n"
                f"- Source: `{projector.state.source}`\n"
                f"- Topology: `{projector.state.topology}`\n"
                f"- Projection: `{projector.state.projection}`\n\n"
                f"{result.markdown()}"
            )
            try:
                path.write_text(text, encoding="utf-8")
                current.message = f"exported: {path}"
            except Exception as exc:
                current.message = f"export failed: {exc}"

        host.key_handlers.update(
            {
                "o": open_dialog,
                "c": code_import_dialog,
                "t": topology_dialog,
                "h": hierarchy_dialog,
                "e": export_dialog,
            }
        )
        host.run(stdscr)

    curses.wrapper(app)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Interactive CW topology View")
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="Optional canonical CW artifact or folder. Use o in the TUI to browse.",
    )
    args = parser.parse_args()

    try:
        run(args.source)
    except Exception as exc:
        print(f"cw-topology-tui: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
