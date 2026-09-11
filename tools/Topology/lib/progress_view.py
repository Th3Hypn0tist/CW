from __future__ import annotations

import curses


def draw_progress(
    stdscr: curses.window,
    title: str,
    percent: int,
    detail: str = "",
) -> None:
    """Draw a small modal 0-100% progress view and return immediately."""
    percent = max(0, min(100, int(percent)))
    height, width = stdscr.getmaxyx()

    if height < 7 or width < 32:
        stdscr.erase()
        text = f"{title}: {percent:3d}% {detail}".strip()
        stdscr.addnstr(0, 0, text, max(0, width - 1))
        stdscr.refresh()
        return

    dialog_width = max(32, min(width - 4, 74))
    dialog_height = 7
    y = max(0, (height - dialog_height) // 2)
    x = max(0, (width - dialog_width) // 2)
    win = curses.newwin(dialog_height, dialog_width, y, x)

    inner_width = max(1, dialog_width - 4)
    bar_width = max(10, dialog_width - 13)
    filled = round(bar_width * percent / 100)
    bar = f"[{'#' * filled}{'-' * (bar_width - filled)}] {percent:3d}%"

    win.erase()
    win.box()
    win.addnstr(0, 2, f" {title} ", inner_width)
    win.addnstr(2, 2, detail, inner_width)
    win.addnstr(4, 2, bar, inner_width)
    win.refresh()
