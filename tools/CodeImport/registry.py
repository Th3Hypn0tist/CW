from __future__ import annotations

from pathlib import Path

from tools.CodeImport.parser import CodeParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, CodeParser] = {}

    def register(self, parser: CodeParser) -> None:
        parser_id = str(parser.id).strip()
        if not parser_id:
            raise ValueError("parser id is required")
        if parser_id in self._parsers:
            raise ValueError(f"parser already registered: {parser_id}")
        self._parsers[parser_id] = parser

    def get(self, parser_id: str) -> CodeParser:
        try:
            return self._parsers[parser_id]
        except KeyError as exc:
            raise KeyError(f"unknown parser: {parser_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._parsers))

    def parsers_for(self, path: Path) -> tuple[CodeParser, ...]:
        return tuple(parser for parser in self._parsers.values() if parser.accepts(path))


def default_registry() -> ParserRegistry:
    from tools.CodeImport.parsers.python_ast import PythonAstParser

    registry = ParserRegistry()
    registry.register(PythonAstParser())
    return registry
