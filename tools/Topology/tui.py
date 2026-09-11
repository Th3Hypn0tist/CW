from __future__ import annotations

import curses
import shutil
import sys
from pathlib import Path

# Support both invocation styles:
#   python3 -m tools.Topology
#   python3 tools/Topology/tui.py
# Direct script execution puts tools/Topology on sys.path, not the repo root.
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from tools.CIC import import_folder
from tools.Topology.lib.curses_view import CursesViewHost
from tools.Topology.lib.projector import TopologyProjector


def run(source: Path | None = None) -> None:
    projector = TopologyProjector(source)

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
            code_folder = current.browse_path(
                stdscr,
                "Code import source folder",
                start=Path.cwd(),
                file_filter=lambda _path: False,
                allow_directories=True,
            )
            if code_folder is None:
                return
            if not code_folder.is_dir():
                current.message = "CIC code import source must be a folder"
                return

            cw_folder = current.browse_path(
                stdscr,
                "Export CIC result to CW folder",
                start=code_folder.parent,
                file_filter=lambda _path: False,
                allow_directories=True,
                allow_new_directory=True,
            )
            if cw_folder is None:
                current.message = "code import cancelled before CW export"
                return
            cw_folder = cw_folder.expanduser().resolve()

            if cw_folder == code_folder:
                current.message = "CW output folder must differ from code folder"
                return
            if cw_folder in code_folder.parents:
                current.message = "CW output folder cannot contain the code folder"
                return
            if code_folder in cw_folder.parents:
                current.message = "CW output folder cannot be inside the code folder"
                return

            if cw_folder.exists():
                if not cw_folder.is_dir():
                    current.message = f"CW output path exists and is not a folder: {cw_folder}"
                    return

                choice = current.choose(
                    stdscr,
                    f"Destination exists: {cw_folder}",
                    ["jyrää", "hylkää"],
                    selected=1,
                )
                if choice is None or choice == 1:
                    current.message = "code import cancelled; existing CW kept"
                    return

                try:
                    shutil.rmtree(cw_folder)
                except Exception as exc:
                    current.message = f"cannot clear destination: {exc}"
                    return

            try:
                result = import_folder(
                    code_folder,
                    cw_folder,
                    force=False,
                )
                projector.open(result.cw_folder)
                current.scroll = 0
                current.message = (
                    f"CIC created: {result.cw_folder}  "
                    f"files={result.files_imported}/{result.files_seen}  "
                    f"shards={result.shard_count} diagnostics={result.diagnostics}"
                )
            except Exception as exc:
                current.message = f"CIC import failed: {exc}"

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
