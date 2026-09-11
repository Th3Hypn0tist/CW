from __future__ import annotations

import curses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


RenderLines = Callable[[], Sequence[str]]
StatusLine = Callable[[], str]
KeyHandler = Callable[["CursesViewHost"], None]
PathFilter = Callable[[Path], bool]


def _clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    return text[:width]


@dataclass
class CursesViewHost:
    """Small reusable curses host for line-oriented View modules.

    The host owns terminal concerns only: scrolling, key dispatch, modal input/list
    dialogs, filesystem browsing, status rendering and the quit sequence.
    Domain/View semantics stay in the caller supplied callbacks.
    """

    title: str
    render_lines: RenderLines
    status_line: StatusLine
    footer: str
    key_handlers: dict[str, KeyHandler] = field(default_factory=dict)
    quit_sequence: str = "qqq"
    scroll: int = 0
    message: str = ""
    _quit_progress: str = ""

    def run(self, stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)

        while True:
            lines = list(self.render_lines())
            self._clamp_scroll(lines, stdscr)
            self._draw(stdscr, lines)

            key = stdscr.get_wch()
            if key == curses.KEY_UP:
                self._quit_progress = ""
                self.scroll = max(0, self.scroll - 1)
                continue
            if key == curses.KEY_DOWN:
                self._quit_progress = ""
                self.scroll += 1
                continue

            if isinstance(key, str):
                if self._consume_quit(key):
                    return
                handler = self.key_handlers.get(key)
                if handler is not None:
                    self._quit_progress = ""
                    handler(self)
                    continue

            self._quit_progress = ""

    def prompt(self, stdscr: curses.window, title: str, initial: str = "") -> str | None:
        height, width = stdscr.getmaxyx()
        dialog_width = max(24, min(width - 4, max(len(title) + 4, 64)))
        dialog_height = 5
        if height < dialog_height + 2 or width < 28:
            self.message = "terminal too small for dialog"
            return None

        y = max(0, (height - dialog_height) // 2)
        x = max(0, (width - dialog_width) // 2)
        win = curses.newwin(dialog_height, dialog_width, y, x)
        win.keypad(True)
        value = list(initial)
        cursor = len(value)

        while True:
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, dialog_width - 4))
            shown = "".join(value)
            win.addnstr(2, 2, shown, max(0, dialog_width - 4))
            win.refresh()

            curses.curs_set(1)
            try:
                win.move(2, min(dialog_width - 3, 2 + cursor))
            except curses.error:
                pass

            key = win.get_wch()
            if key in ("\n", "\r") or key == curses.KEY_ENTER:
                curses.curs_set(0)
                return "".join(value).strip()
            if key == "\x1b":
                curses.curs_set(0)
                return None
            if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                if cursor > 0:
                    del value[cursor - 1]
                    cursor -= 1
                continue
            if key == curses.KEY_LEFT:
                cursor = max(0, cursor - 1)
                continue
            if key == curses.KEY_RIGHT:
                cursor = min(len(value), cursor + 1)
                continue
            if isinstance(key, str) and key.isprintable():
                value.insert(cursor, key)
                cursor += 1

    def choose(
        self,
        stdscr: curses.window,
        title: str,
        options: Sequence[str],
        selected: int = 0,
    ) -> int | None:
        if not options:
            self.message = "no choices available"
            return None

        height, width = stdscr.getmaxyx()
        dialog_width = max(
            28,
            min(width - 4, max(len(title) + 4, *(len(x) + 4 for x in options))),
        )
        visible = max(1, min(len(options), height - 6, 16))
        dialog_height = visible + 2
        if height < 6 or width < 32:
            self.message = "terminal too small for dialog"
            return None

        y = max(0, (height - dialog_height) // 2)
        x = max(0, (width - dialog_width) // 2)
        win = curses.newwin(dialog_height, dialog_width, y, x)
        win.keypad(True)

        index = min(max(0, selected), len(options) - 1)
        offset = min(max(0, index - visible + 1), max(0, len(options) - visible))

        while True:
            if index < offset:
                offset = index
            elif index >= offset + visible:
                offset = index - visible + 1

            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, dialog_width - 4))
            for row, option_index in enumerate(
                range(offset, min(len(options), offset + visible)), start=1
            ):
                option = options[option_index]
                attr = curses.A_REVERSE if option_index == index else curses.A_NORMAL
                win.addnstr(row, 2, option, max(0, dialog_width - 4), attr)
            win.refresh()

            key = win.get_wch()
            if key == curses.KEY_UP:
                index = max(0, index - 1)
                continue
            if key == curses.KEY_DOWN:
                index = min(len(options) - 1, index + 1)
                continue
            if key in ("\n", "\r") or key == curses.KEY_ENTER:
                return index
            if key == "\x1b":
                return None

    def browse_path(
        self,
        stdscr: curses.window,
        title: str,
        *,
        start: Path | None = None,
        file_filter: PathFilter | None = None,
        allow_directories: bool = True,
        allow_new_directory: bool = False,
    ) -> Path | None:
        """Browse the filesystem and return a selected file or directory.

        Directories are navigation targets. When ``allow_directories`` is true,
        ``[open this folder]`` selects the currently displayed directory. When
        ``allow_new_directory`` is true, ``[new dir]`` asks for a child directory
        name and returns that path without creating it. This lets a caller hand
        the path to the component that owns creation semantics. The optional file
        filter applies only to files, keeping this host domain-neutral.
        """

        current = (start or Path.cwd()).expanduser()
        if current.is_file():
            current = current.parent
        if not current.exists() or not current.is_dir():
            current = Path.cwd()
        current = current.resolve()
        index = 0
        offset = 0

        while True:
            entries: list[tuple[str, str, Path]] = []
            if allow_directories:
                entries.append(("select", "[open this folder]", current))
            if allow_new_directory:
                entries.append(("new_directory", "[new dir]", current))
            if current.parent != current:
                entries.append(("parent", "../", current.parent))

            try:
                children = sorted(
                    current.iterdir(),
                    key=lambda path: (not path.is_dir(), path.name.casefold(), path.name),
                )
            except OSError as exc:
                self.message = f"browse failed: {exc}"
                return None

            for path in children:
                if path.is_dir():
                    entries.append(("directory", f"{path.name}/", path))
                elif file_filter is None or file_filter(path):
                    entries.append(("file", path.name, path))

            if not entries:
                self.message = "folder is empty"
                return None

            height, width = stdscr.getmaxyx()
            if height < 7 or width < 32:
                self.message = "terminal too small for browser"
                return None

            visible = max(1, min(len(entries), height - 7, 20))
            dialog_height = visible + 3
            dialog_width = max(32, min(width - 4, max(64, len(title) + 4)))
            y = max(0, (height - dialog_height) // 2)
            x = max(0, (width - dialog_width) // 2)
            win = curses.newwin(dialog_height, dialog_width, y, x)
            win.keypad(True)

            index = min(index, len(entries) - 1)
            if index < offset:
                offset = index
            elif index >= offset + visible:
                offset = index - visible + 1
            offset = min(max(0, offset), max(0, len(entries) - visible))

            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, dialog_width - 4))
            win.addnstr(1, 2, str(current), max(0, dialog_width - 4), curses.A_DIM)
            for row, entry_index in enumerate(
                range(offset, min(len(entries), offset + visible)), start=2
            ):
                _, label, _ = entries[entry_index]
                attr = curses.A_REVERSE if entry_index == index else curses.A_NORMAL
                win.addnstr(row, 2, label, max(0, dialog_width - 4), attr)
            win.refresh()

            key = win.get_wch()
            if key == curses.KEY_UP:
                index = max(0, index - 1)
                continue
            if key == curses.KEY_DOWN:
                index = min(len(entries) - 1, index + 1)
                continue
            if key == "\x1b":
                return None
            if key not in ("\n", "\r") and key != curses.KEY_ENTER:
                continue

            kind, _, path = entries[index]
            if kind in {"parent", "directory"}:
                current = path.resolve()
                index = 0
                offset = 0
                continue
            if kind == "new_directory":
                name = self.prompt(stdscr, "New directory name")
                if name is None:
                    continue
                name = name.strip()
                if not name:
                    self.message = "directory name is required"
                    continue
                candidate_name = Path(name)
                if candidate_name.name != name or name in {".", ".."}:
                    self.message = "enter one directory name, not a path"
                    continue
                return (current / name).resolve()
            return path.resolve()

    def _consume_quit(self, key: str) -> bool:
        if not self.quit_sequence:
            return False

        expected_index = len(self._quit_progress)
        if (
            expected_index < len(self.quit_sequence)
            and key == self.quit_sequence[expected_index]
        ):
            self._quit_progress += key
            return self._quit_progress == self.quit_sequence

        self._quit_progress = (
            self.quit_sequence[:1] if key == self.quit_sequence[:1] else ""
        )
        return False

    def _content_height(self, stdscr: curses.window) -> int:
        height, _ = stdscr.getmaxyx()
        return max(1, height - 4)

    def _clamp_scroll(self, lines: Sequence[str], stdscr: curses.window) -> None:
        max_scroll = max(0, len(lines) - self._content_height(stdscr))
        self.scroll = min(max(0, self.scroll), max_scroll)

    def _draw(self, stdscr: curses.window, lines: Sequence[str]) -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        if height < 4 or width < 8:
            stdscr.addnstr(0, 0, "terminal too small", max(0, width - 1))
            stdscr.refresh()
            return

        stdscr.addnstr(0, 0, self.title, width - 1, curses.A_BOLD)
        stdscr.addnstr(1, 0, self.status_line(), width - 1)

        content_height = self._content_height(stdscr)
        visible = lines[self.scroll : self.scroll + content_height]
        for row, line in enumerate(visible, start=2):
            if row >= height - 2:
                break
            stdscr.addnstr(row, 0, _clip(str(line), width - 1), width - 1)

        message = self.message
        if self._quit_progress:
            remaining = len(self.quit_sequence) - len(self._quit_progress)
            message = f"quit: {self._quit_progress}{'_' * remaining}"
        stdscr.addnstr(height - 2, 0, message, width - 1)
        stdscr.addnstr(height - 1, 0, self.footer, width - 1, curses.A_DIM)
        stdscr.refresh()
