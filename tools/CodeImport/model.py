from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CodeNode:
    ref: str
    name: str
    kind: str
    source_path: Path | None = None


@dataclass(frozen=True)
class CodeEdge:
    ref: str
    relation: str
    parent_ref: str
    child_ref: str
    source_path: Path | None = None
    line: int | None = None


@dataclass(frozen=True)
class ImportFinding:
    parser: str
    source_path: Path
    message: str
    line: int | None = None


@dataclass
class CodeImportResult:
    source: Path
    nodes: dict[str, CodeNode] = field(default_factory=dict)
    edges: list[CodeEdge] = field(default_factory=list)
    findings: list[ImportFinding] = field(default_factory=list)

    @property
    def relations(self) -> tuple[str, ...]:
        return tuple(sorted({edge.relation for edge in self.edges}))
