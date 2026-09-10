from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectionResult:
    """Representation-neutral projection result.

    Projection modules return data. They do not print, read files, own curses, or
    decide command syntax. That keeps them directly wrappable by shell commands,
    AIGMos commands, View modules, exporters, or other hosts.
    """

    name: str
    lines: tuple[str, ...]
    markdown_fence: str = "text"

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def markdown(self) -> str:
        return f"```{self.markdown_fence}\n{self.text}\n```\n"
