from __future__ import annotations

from pathlib import Path
from typing import Protocol

from tools.CodeImport.model import CodeImportResult


class CodeParser(Protocol):
    """Language parser contract used by the reusable CodeImport library."""

    id: str
    language: str
    suffixes: tuple[str, ...]

    def accepts(self, path: Path) -> bool:
        ...

    def parse_file(self, path: Path, *, root: Path) -> CodeImportResult:
        ...
