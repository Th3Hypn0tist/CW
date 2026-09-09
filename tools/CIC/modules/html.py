from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


_VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
})


def _attr_map(attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
    return {str(name): value for name, value in attrs}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.elements: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.text_nodes: list[dict[str, Any]] = []
        self.entities: list[dict[str, Any]] = []
        self.declarations: list[dict[str, Any]] = []
        self.references: list[dict[str, Any]] = []
        self.inline_events: list[dict[str, Any]] = []
        self.stack: list[int] = []
        self.diagnostics: list[dict[str, Any]] = []

    def _position(self) -> dict[str, int]:
        line, column = self.getpos()
        return {"line": line, "column": column}

    def _parent_index(self) -> int | None:
        return self.stack[-1] if self.stack else None

    def _record_element(self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> int:
        normalized = tag.lower()
        attr_values = _attr_map(attrs)
        index = len(self.elements)
        record = {
            "kind": "element",
            "index": index,
            "tag": normalized,
            "parent_index": self._parent_index(),
            "attributes": [{"name": name, "value": value} for name, value in attrs],
            "id": attr_values.get("id"),
            "classes": str(attr_values.get("class") or "").split(),
            "self_closing": self_closing or normalized in _VOID_ELEMENTS,
            "span": self._position(),
        }
        self.elements.append(record)

        reference_attrs = {
            "script": ("src",),
            "link": ("href",),
            "img": ("src", "srcset"),
            "source": ("src", "srcset"),
            "a": ("href",),
            "form": ("action",),
            "iframe": ("src",),
        }
        for attr_name in reference_attrs.get(normalized, ()):
            value = attr_values.get(attr_name)
            if isinstance(value, str) and value:
                self.references.append({
                    "kind": "html_reference",
                    "tag": normalized,
                    "attribute": attr_name,
                    "target": value,
                    "element_index": index,
                    "span": self._position(),
                })

        for name, value in attrs:
            lowered = name.lower()
            if lowered.startswith("on") and len(lowered) > 2:
                self.inline_events.append({
                    "kind": "inline_event_attribute",
                    "event_name": lowered[2:],
                    "attribute": lowered,
                    "source": value,
                    "element_index": index,
                    "span": self._position(),
                    "canonical_semantic_authority": False,
                })
        return index

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        index = self._record_element(tag, attrs, self_closing=False)
        if self.elements[index]["self_closing"] is False:
            self.stack.append(index)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_element(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if not self.stack:
            self.diagnostics.append({
                "code": "UNMATCHED_END_TAG",
                "message": f"closing tag has no open element: {normalized}",
                **self._position(),
            })
            return
        match_offset = None
        for offset in range(len(self.stack) - 1, -1, -1):
            element = self.elements[self.stack[offset]]
            if element["tag"] == normalized:
                match_offset = offset
                break
        if match_offset is None:
            self.diagnostics.append({
                "code": "UNMATCHED_END_TAG",
                "message": f"closing tag does not match open stack: {normalized}",
                **self._position(),
            })
            return
        if match_offset != len(self.stack) - 1:
            for orphan_index in self.stack[match_offset + 1:]:
                self.diagnostics.append({
                    "code": "IMPLICITLY_CLOSED_TAG",
                    "message": f"element implicitly closed before </{normalized}>: {self.elements[orphan_index]['tag']}",
                    **self._position(),
                })
        del self.stack[match_offset:]

    def handle_data(self, data: str) -> None:
        if not data:
            return
        self.text_nodes.append({
            "kind": "text",
            "parent_index": self._parent_index(),
            "text": data,
            "whitespace_only": data.isspace(),
            "span": self._position(),
        })

    def handle_comment(self, data: str) -> None:
        self.comments.append({"kind": "comment", "text": data, "span": self._position()})

    def handle_decl(self, decl: str) -> None:
        self.declarations.append({"kind": "declaration", "value": decl, "span": self._position()})

    def handle_entityref(self, name: str) -> None:
        self.entities.append({"kind": "entity_ref", "name": name, "span": self._position()})

    def handle_charref(self, name: str) -> None:
        self.entities.append({"kind": "char_ref", "name": name, "span": self._position()})

    def unknown_decl(self, data: str) -> None:
        self.declarations.append({"kind": "unknown_declaration", "value": data, "span": self._position()})


def extract_html(path: str, source: str) -> dict[str, Any]:
    parser = _Extractor()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:
        parser.diagnostics.append({"code": "HTML_PARSE_ERROR", "message": str(exc)})

    for index in parser.stack:
        parser.diagnostics.append({
            "code": "UNCLOSED_TAG",
            "message": f"open element not explicitly closed: {parser.elements[index]['tag']}",
            "element_index": index,
        })

    ids: dict[str, list[int]] = {}
    for element in parser.elements:
        value = element.get("id")
        if isinstance(value, str) and value:
            ids.setdefault(value, []).append(int(element["index"]))
    for value, indexes in sorted(ids.items()):
        if len(indexes) > 1:
            parser.diagnostics.append({
                "code": "DUPLICATE_HTML_ID",
                "message": f"duplicate HTML id: {value}",
                "element_indexes": indexes,
            })

    return {
        "language_id": "html",
        "parser_id": "cic-html-stdlib-1",
        "parser_available": True,
        "diagnostics": parser.diagnostics,
        "symbols": parser.elements,
        "imports": [],
        "exports": [],
        "evidence": [
            *parser.declarations,
            *parser.comments,
            *parser.text_nodes,
            *parser.entities,
            *parser.references,
            *parser.inline_events,
        ],
        "html": {
            "elements": parser.elements,
            "references": parser.references,
            "inline_event_attributes": parser.inline_events,
            "comments": parser.comments,
            "text_nodes": parser.text_nodes,
            "declarations": parser.declarations,
            "entity_references": parser.entities,
        },
    }
