from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


def _tokenize(source: str) -> tuple[list[Token], list[dict[str, Any]]]:
    tokens: list[Token] = []
    diagnostics: list[dict[str, Any]] = []
    i = 0
    line = 1
    column = 0
    length = len(source)

    def advance(text: str) -> None:
        nonlocal line, column
        parts = text.split("\n")
        if len(parts) == 1:
            column += len(text)
        else:
            line += len(parts) - 1
            column = len(parts[-1])

    while i < length:
        ch = source[i]
        start_line, start_column = line, column
        if ch.isspace():
            j = i + 1
            while j < length and source[j].isspace():
                j += 1
            text = source[i:j]
            tokens.append(Token("whitespace", text, start_line, start_column))
            advance(text)
            i = j
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            if end < 0:
                text = source[i:]
                tokens.append(Token("comment", text, start_line, start_column))
                diagnostics.append({"code": "UNCLOSED_CSS_COMMENT", "message": "CSS comment is not closed", "line": start_line, "column": start_column})
                break
            end += 2
            text = source[i:end]
            tokens.append(Token("comment", text, start_line, start_column))
            advance(text)
            i = end
            continue
        if ch in {'"', "'"}:
            quote = ch
            j = i + 1
            escaped = False
            while j < length:
                current = source[j]
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    j += 1
                    break
                j += 1
            text = source[i:j]
            if not text.endswith(quote):
                diagnostics.append({"code": "UNCLOSED_CSS_STRING", "message": "CSS string is not closed", "line": start_line, "column": start_column})
            tokens.append(Token("string", text, start_line, start_column))
            advance(text)
            i = j
            continue
        if ch in "{}:;(),[]":
            tokens.append(Token("punct", ch, start_line, start_column))
            advance(ch)
            i += 1
            continue
        if ch == "@":
            j = i + 1
            while j < length and (source[j].isalnum() or source[j] in "-_\\"):
                j += 1
            text = source[i:j]
            tokens.append(Token("at_keyword", text, start_line, start_column))
            advance(text)
            i = j
            continue
        j = i + 1
        while j < length:
            current = source[j]
            if current.isspace() or current in "{}:;(),[]'\"" or source.startswith("/*", j):
                break
            j += 1
        text = source[i:j]
        tokens.append(Token("word", text, start_line, start_column))
        advance(text)
        i = j
    return tokens, diagnostics


def _compact(tokens: list[Token]) -> str:
    parts: list[str] = []
    pending_space = False
    for token in tokens:
        if token.kind == "comment":
            continue
        if token.kind == "whitespace":
            pending_space = True
            continue
        if pending_space and parts and token.value not in ":;,)}]":
            parts.append(" ")
        parts.append(token.value)
        pending_space = False
    return "".join(parts).strip()


def _split_top_level(tokens: list[Token], delimiter: str) -> list[list[Token]]:
    result: list[list[Token]] = []
    current: list[Token] = []
    depth = 0
    for token in tokens:
        if token.value in "([":
            depth += 1
        elif token.value in ")]" and depth > 0:
            depth -= 1
        if token.value == delimiter and depth == 0:
            result.append(current)
            current = []
        else:
            current.append(token)
    result.append(current)
    return result


def _declarations(tokens: list[Token]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for part in _split_top_level(tokens, ";"):
        significant = [token for token in part if token.kind not in {"whitespace", "comment"}]
        if not significant:
            continue
        depth = 0
        colon_index = None
        for index, token in enumerate(significant):
            if token.value in "([":
                depth += 1
            elif token.value in ")]" and depth > 0:
                depth -= 1
            elif token.value == ":" and depth == 0:
                colon_index = index
                break
        if colon_index is None:
            continue
        name_tokens = significant[:colon_index]
        value_tokens = significant[colon_index + 1:]
        name = _compact(name_tokens)
        value = _compact(value_tokens)
        if not name:
            continue
        important = False
        normalized_value = value
        if value.lower().endswith("!important"):
            important = True
            normalized_value = value[: -len("!important")].rstrip()
        result.append({
            "kind": "declaration",
            "name": name,
            "value": normalized_value,
            "important": important,
            "line": significant[0].line,
            "column": significant[0].column,
        })
    return result


def _extract_urls(value: str) -> list[str]:
    result: list[str] = []
    lower = value.lower()
    offset = 0
    while True:
        start = lower.find("url(", offset)
        if start < 0:
            break
        i = start + 4
        depth = 1
        quote: str | None = None
        escaped = False
        while i < len(value) and depth:
            ch = value[i]
            if quote is not None:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
            else:
                if ch in {'"', "'"}:
                    quote = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        raw = value[start + 4:i - 1].strip() if depth == 0 else value[start + 4:].strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            raw = raw[1:-1]
        if raw:
            result.append(raw)
        offset = max(i, start + 4)
    return result


def extract_css(path: str, source: str) -> dict[str, Any]:
    tokens, diagnostics = _tokenize(source)
    rules: list[dict[str, Any]] = []
    at_rules: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    comments = [
        {"kind": "comment", "text": token.value[2:-2] if token.value.endswith("*/") else token.value[2:], "line": token.line, "column": token.column}
        for token in tokens if token.kind == "comment"
    ]

    i = 0
    while i < len(tokens):
        while i < len(tokens) and tokens[i].kind in {"whitespace", "comment"}:
            i += 1
        if i >= len(tokens):
            break
        start = i
        depth = 0
        open_index = None
        semicolon_index = None
        while i < len(tokens):
            token = tokens[i]
            if token.value in "([":
                depth += 1
            elif token.value in ")]" and depth > 0:
                depth -= 1
            elif depth == 0 and token.value == "{":
                open_index = i
                break
            elif depth == 0 and token.value == ";":
                semicolon_index = i
                break
            i += 1

        prelude_end = open_index if open_index is not None else semicolon_index
        if prelude_end is None:
            prelude_end = len(tokens)
        prelude_tokens = tokens[start:prelude_end]
        prelude = _compact(prelude_tokens)
        first = next((token for token in prelude_tokens if token.kind not in {"whitespace", "comment"}), None)

        if open_index is None:
            if first and first.kind == "at_keyword":
                at_rules.append({
                    "kind": "at_rule",
                    "name": first.value[1:],
                    "prelude": _compact(prelude_tokens[1:]),
                    "block": None,
                    "line": first.line,
                    "column": first.column,
                })
                if first.value.lower() in {"@import", "@namespace"}:
                    target = _compact(prelude_tokens[1:]).strip()
                    if target:
                        references.append({"kind": "css_reference", "reference_type": first.value[1:].lower(), "target": target, "line": first.line, "column": first.column})
            i = (semicolon_index + 1) if semicolon_index is not None else len(tokens)
            continue

        block_start = open_index + 1
        i = block_start
        brace_depth = 1
        while i < len(tokens) and brace_depth:
            if tokens[i].value == "{":
                brace_depth += 1
            elif tokens[i].value == "}":
                brace_depth -= 1
            i += 1
        if brace_depth:
            diagnostics.append({"code": "UNCLOSED_CSS_BLOCK", "message": f"CSS block is not closed: {prelude}", "line": first.line if first else None, "column": first.column if first else None})
            block_end = len(tokens)
        else:
            block_end = i - 1
        body = tokens[block_start:block_end]

        if first and first.kind == "at_keyword":
            name = first.value[1:]
            at_rules.append({
                "kind": "at_rule",
                "name": name,
                "prelude": _compact(prelude_tokens[1:]),
                "block": _compact(body),
                "line": first.line,
                "column": first.column,
            })
        else:
            selectors = [_compact(part) for part in _split_top_level(prelude_tokens, ",") if _compact(part)]
            declarations = _declarations(body)
            rule = {
                "kind": "style_rule",
                "selectors": selectors,
                "declarations": declarations,
                "line": first.line if first else None,
                "column": first.column if first else None,
            }
            rules.append(rule)
            for declaration in declarations:
                for target in _extract_urls(str(declaration.get("value") or "")):
                    references.append({
                        "kind": "css_reference",
                        "reference_type": "url",
                        "property": declaration["name"],
                        "target": target,
                        "line": declaration["line"],
                        "column": declaration["column"],
                    })

    return {
        "language_id": "css",
        "parser_id": "cic-css-stdlib-1",
        "parser_available": True,
        "diagnostics": diagnostics,
        "symbols": rules,
        "imports": [],
        "exports": [],
        "evidence": [*comments, *at_rules, *references],
        "css": {
            "rules": rules,
            "at_rules": at_rules,
            "references": references,
            "comments": comments,
            "token_count": len(tokens),
        },
    }
