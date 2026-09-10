from __future__ import annotations

from pathlib import Path

from tools.CodeImport.model import CodeImportResult
from tools.CodeImport.registry import ParserRegistry, default_registry


class CodeImporter:
    """Reusable multi-language code import service.

    Parser selection is an implementation concern only. Imported relations remain
    explicit outputs of the selected parser and are not canonical CW semantics.
    """

    def __init__(self, registry: ParserRegistry | None = None) -> None:
        self.registry = registry or default_registry()

    def import_source(self, source: Path) -> CodeImportResult:
        source = source.expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(source)

        root = source if source.is_dir() else source.parent
        files = [source] if source.is_file() else sorted(
            (path for path in source.rglob("*") if path.is_file()),
            key=lambda path: path.as_posix(),
        )

        combined = CodeImportResult(source=source)
        for path in files:
            parsers = self.registry.parsers_for(path)
            if not parsers:
                continue
            if len(parsers) > 1:
                raise ValueError(
                    f"multiple parsers accept {path}: "
                    + ", ".join(parser.id for parser in parsers)
                )
            partial = parsers[0].parse_file(path, root=root)
            for ref, node in partial.nodes.items():
                combined.nodes.setdefault(ref, node)
            combined.edges.extend(partial.edges)
            combined.findings.extend(partial.findings)

        combined.edges.sort(
            key=lambda edge: (edge.relation, edge.parent_ref, edge.child_ref, edge.ref)
        )
        return combined
