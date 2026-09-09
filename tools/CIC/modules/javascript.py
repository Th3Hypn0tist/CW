from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_KEYWORDS = frozenset({
    "async", "await", "break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete",
    "do", "else", "export", "extends", "finally", "for", "from", "function", "get", "if", "import", "in", "instanceof",
    "let", "new", "of", "return", "set", "static", "super", "switch", "this", "throw", "try", "typeof", "var", "void",
    "while", "with", "yield", "true", "false", "null", "undefined", "as",
})


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int
    start: int
    end: int


def _lex(source: str) -> tuple[list[Token], list[dict[str, Any]]]:
    tokens: list[Token] = []
    diagnostics: list[dict[str, Any]] = []
    i = 0
    line = 1
    column = 0
    n = len(source)

    def emit(kind: str, start: int, end: int, start_line: int, start_column: int) -> None:
        tokens.append(Token(kind, source[start:end], start_line, start_column, start, end))

    def advance(text: str) -> None:
        nonlocal line, column
        parts = text.split("\n")
        if len(parts) == 1:
            column += len(text)
        else:
            line += len(parts) - 1
            column = len(parts[-1])

    while i < n:
        ch = source[i]
        start, start_line, start_column = i, line, column
        if ch.isspace():
            j = i + 1
            while j < n and source[j].isspace():
                j += 1
            advance(source[i:j])
            i = j
            continue
        if source.startswith("//", i):
            j = source.find("\n", i + 2)
            if j < 0:
                j = n
            emit("comment", i, j, start_line, start_column)
            advance(source[i:j])
            i = j
            continue
        if source.startswith("/*", i):
            j = source.find("*/", i + 2)
            if j < 0:
                emit("comment", i, n, start_line, start_column)
                diagnostics.append({"code": "UNCLOSED_JS_COMMENT", "message": "JavaScript block comment is not closed", "line": start_line, "column": start_column})
                break
            j += 2
            emit("comment", i, j, start_line, start_column)
            advance(source[i:j])
            i = j
            continue
        if ch in {'"', "'", '`'}:
            quote = ch
            j = i + 1
            escaped = False
            template_depth = 0
            while j < n:
                current = source[j]
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif quote == '`' and source.startswith("${", j):
                    template_depth += 1
                    j += 1
                elif quote == '`' and current == "}" and template_depth:
                    template_depth -= 1
                elif current == quote and template_depth == 0:
                    j += 1
                    break
                j += 1
            if j > n or not source[i:j].endswith(quote):
                diagnostics.append({"code": "UNCLOSED_JS_STRING", "message": "JavaScript string/template is not closed", "line": start_line, "column": start_column})
                j = min(j, n)
            emit("string", i, j, start_line, start_column)
            advance(source[i:j])
            i = j
            continue
        if ch.isalpha() or ch in "_$":
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] in "_$"):
                j += 1
            text = source[i:j]
            emit("keyword" if text in _KEYWORDS else "identifier", i, j, start_line, start_column)
            advance(text)
            i = j
            continue
        if ch.isdigit():
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] in ".xXoObBeE_+-"):
                if source[j] in "+-" and source[j - 1] not in "eE":
                    break
                j += 1
            emit("number", i, j, start_line, start_column)
            advance(source[i:j])
            i = j
            continue
        matched = None
        for op in ("===", "!==", ">>>", "**=", "&&=", "||=", "??=", "=>", "==", "!=", "<=", ">=", "++", "--", "&&", "||", "??", "?.", "**", "+=", "-=", "*=", "/=", "%=", "<<", ">>", "&=", "|=", "^="):
            if source.startswith(op, i):
                matched = op
                break
        if matched:
            emit("operator", i, i + len(matched), start_line, start_column)
            advance(matched)
            i += len(matched)
            continue
        kind = "punct" if ch in "{}()[];,.?:" else "operator"
        emit(kind, i, i + 1, start_line, start_column)
        advance(ch)
        i += 1
    return tokens, diagnostics


def _significant(tokens: list[Token]) -> list[Token]:
    return [token for token in tokens if token.kind != "comment"]


def _match_pairs(tokens: list[Token]) -> tuple[dict[int, int], list[dict[str, Any]]]:
    opens = {"(": ")", "[": "]", "{": "}"}
    closes = {value: key for key, value in opens.items()}
    stack: list[tuple[str, int]] = []
    pairs: dict[int, int] = {}
    diagnostics: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value in opens:
            stack.append((token.value, index))
        elif token.value in closes:
            if not stack or stack[-1][0] != closes[token.value]:
                diagnostics.append({"code": "UNMATCHED_JS_DELIMITER", "message": f"unmatched delimiter: {token.value}", "line": token.line, "column": token.column})
                continue
            _, start = stack.pop()
            pairs[start] = index
            pairs[index] = start
    for value, index in stack:
        token = tokens[index]
        diagnostics.append({"code": "UNCLOSED_JS_DELIMITER", "message": f"delimiter is not closed: {value}", "line": token.line, "column": token.column})
    return pairs, diagnostics


def _span(token: Token) -> dict[str, int]:
    return {"line": token.line, "column": token.column}


def _token_text(source: str, tokens: list[Token]) -> str:
    if not tokens:
        return ""
    return source[tokens[0].start:tokens[-1].end]


def _split(tokens: list[Token], delimiter: str, pairs: dict[int, int], offset: int = 0) -> list[list[Token]]:
    result: list[list[Token]] = []
    current: list[Token] = []
    depth = 0
    for token in tokens:
        if token.value in "([{":
            depth += 1
        elif token.value in ")]}":
            depth = max(depth - 1, 0)
        if token.value == delimiter and depth == 0:
            result.append(current)
            current = []
        else:
            current.append(token)
    result.append(current)
    return result


def _parameter_records(tokens: list[Token], source: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for part in _split(tokens, ",", {}):
        part = [token for token in part if token.kind != "comment"]
        if not part:
            continue
        name = None
        for token in part:
            if token.kind == "identifier":
                name = token.value
                break
        if name:
            result.append({
                "name": name,
                "kind": "positional",
                "annotation": None,
                "has_default": any(token.value == "=" for token in part),
                "span": _span(part[0]),
            })
        else:
            result.append({
                "name": _token_text(source, part).strip(),
                "kind": "pattern",
                "annotation": None,
                "has_default": any(token.value == "=" for token in part),
                "span": _span(part[0]),
            })
    return result


def _call_target(tokens: list[Token], call_paren_index: int) -> str | None:
    if call_paren_index <= 0:
        return None
    j = call_paren_index - 1
    if tokens[j].value == "?." and j > 0:
        j -= 1
    parts: list[str] = []
    expect_name = True
    while j >= 0:
        token = tokens[j]
        if expect_name:
            if token.kind in {"identifier", "keyword"} and token.value not in {"return", "if", "while", "for", "switch", "catch", "function"}:
                parts.append(token.value)
                expect_name = False
                j -= 1
                continue
            break
        if token.value in {".", "?."}:
            parts.append(".")
            expect_name = True
            j -= 1
            continue
        break
    if not parts or expect_name:
        return None
    return "".join(reversed(parts))


def _logic_facts(tokens: list[Token], source: str) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    writes: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    operators: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    loops: list[dict[str, Any]] = []
    returns: list[dict[str, Any]] = []
    raises: list[dict[str, Any]] = []
    awaits: list[dict[str, Any]] = []
    yields: list[dict[str, Any]] = []
    reads: list[dict[str, Any]] = []

    declaration_mode = False
    for index, token in enumerate(tokens):
        if token.value in {"let", "const", "var"}:
            declaration_mode = True
            continue
        if declaration_mode and token.kind == "identifier":
            writes.append({"name": token.value, "span": _span(token)})
            if index + 1 < len(tokens) and tokens[index + 1].value == "=":
                assignments.append({"targets": [token.value], "declaration": True, "span": _span(token)})
            declaration_mode = False
        if token.kind == "identifier":
            reads.append({"name": token.value, "span": _span(token)})
        if token.value == "(" and index > 0:
            target = _call_target(tokens, index)
            previous = tokens[index - 1].value if index else None
            if target and previous not in {"if", "while", "for", "switch", "catch", "function"}:
                calls.append({"target": target, "args": None, "kwargs": [], "span": _span(token), "kind": "call"})
        if token.value in {"=", "+=", "-=", "*=", "/=", "%="} and index > 0:
            lhs = tokens[index - 1]
            if lhs.kind == "identifier":
                assignments.append({"targets": [lhs.value], "operator": token.value, "span": _span(token)})
                writes.append({"name": lhs.value, "span": _span(lhs)})
        if token.kind == "operator":
            operators.append({"operator": token.value, "span": _span(token)})
            if token.value in {"==", "===", "!=", "!==", "<", "<=", ">", ">=", "in", "instanceof"}:
                comparisons.append({"operators": [token.value], "span": _span(token)})
        if token.value in {"if", "switch", "catch"}:
            branches.append({"kind": token.value, "span": _span(token)})
        if token.value in {"for", "while", "do"}:
            loops.append({"kind": token.value, "span": _span(token)})
        if token.value == "return":
            returns.append({"span": _span(token)})
        if token.value == "throw":
            raises.append({"span": _span(token)})
        if token.value == "await":
            awaits.append({"span": _span(token)})
        if token.value == "yield":
            yields.append({"span": _span(token)})

    return {
        "calls": calls,
        "reads": reads,
        "writes": writes,
        "assignments": assignments,
        "operators": operators,
        "comparisons": comparisons,
        "branches": branches,
        "loops": loops,
        "returns": returns,
        "raises": raises,
        "awaits": awaits,
        "yields": yields,
        "lambdas": [],
    }


def _function_record(
    tokens: list[Token],
    source: str,
    pairs: dict[int, int],
    start: int,
    *,
    owner: str | None = None,
    forced_name: str | None = None,
    method: bool = False,
) -> tuple[dict[str, Any] | None, int]:
    i = start
    async_flag = tokens[i].value == "async"
    if async_flag:
        i += 1
    if i >= len(tokens) or tokens[i].value != "function":
        return None, start + 1
    i += 1
    generator = False
    if i < len(tokens) and tokens[i].value == "*":
        generator = True
        i += 1
    name = forced_name
    if i < len(tokens) and tokens[i].kind == "identifier":
        name = tokens[i].value
        i += 1
    if not name:
        name = "<anonymous>"
    if i >= len(tokens) or tokens[i].value != "(":
        return None, start + 1
    close_params = pairs.get(i)
    if close_params is None:
        return None, start + 1
    params = _parameter_records(tokens[i + 1:close_params], source)
    body_open = close_params + 1
    if body_open >= len(tokens) or tokens[body_open].value != "{":
        return None, close_params + 1
    body_close = pairs.get(body_open)
    if body_close is None:
        return None, body_open + 1
    qualified = f"{owner}.{name}" if owner else name
    body_tokens = tokens[body_open + 1:body_close]
    nested = _extract_nested_functions(body_tokens, source, owner=qualified)
    return {
        "kind": "method" if method else "function",
        "name": name,
        "owner": owner,
        "qualified_name": qualified,
        "async": async_flag,
        "generator": generator,
        "parameters": params,
        "returns_annotation": None,
        "decorators": [],
        "span": _span(tokens[start]),
        "source": source[tokens[start].start:tokens[body_close].end],
        "source_state": "active",
        "decomposition_state": "not_decomposed",
        "primitive_decomposition": {
            "primitive_set_ref": "CW_LOGIC_PRIMITIVES",
            "decomposition_state": "not_decomposed",
            "body": [],
            "unresolved": [{"reason": "JAVASCRIPT_PRIMITIVE_COMPILER_NOT_CONNECTED"}],
            "canonical_ready": False,
            "authority": "implementation_evidence",
        },
        "nested_functions": nested,
        "logic": _logic_facts(body_tokens, source),
    }, body_close + 1


def _extract_nested_functions(tokens: list[Token], source: str, *, owner: str) -> list[dict[str, Any]]:
    pairs, _ = _match_pairs(tokens)
    result: list[dict[str, Any]] = []
    i = 0
    while i < len(tokens):
        if tokens[i].value == "function" or (tokens[i].value == "async" and i + 1 < len(tokens) and tokens[i + 1].value == "function"):
            record, next_index = _function_record(tokens, source, pairs, i, owner=f"{owner}.<locals>")
            if record:
                result.append(record)
                i = next_index
                continue
        i += 1
    return result


def _import_record(tokens: list[Token], source: str, start: int) -> tuple[dict[str, Any] | None, int]:
    i = start + 1
    names: list[dict[str, Any]] = []
    module = None
    if i < len(tokens) and tokens[i].kind == "string":
        module = tokens[i].value[1:-1]
        return {"kind": "import", "module": module, "names": [], "span": _span(tokens[start])}, i + 1
    if i < len(tokens) and tokens[i].kind == "identifier":
        local = tokens[i].value
        names.append({"imported": "default", "local": local, "kind": "ImportDefaultSpecifier"})
        i += 1
        if i < len(tokens) and tokens[i].value == ",":
            i += 1
    if i < len(tokens) and tokens[i].value == "*":
        i += 1
        if i < len(tokens) and tokens[i].value == "as":
            i += 1
        if i < len(tokens) and tokens[i].kind == "identifier":
            names.append({"imported": "*", "local": tokens[i].value, "kind": "ImportNamespaceSpecifier"})
            i += 1
    elif i < len(tokens) and tokens[i].value == "{":
        i += 1
        while i < len(tokens) and tokens[i].value != "}":
            if tokens[i].kind in {"identifier", "keyword"}:
                imported = tokens[i].value
                local = imported
                i += 1
                if i < len(tokens) and tokens[i].value == "as":
                    i += 1
                    if i < len(tokens) and tokens[i].kind == "identifier":
                        local = tokens[i].value
                        i += 1
                names.append({"imported": imported, "local": local, "kind": "ImportSpecifier"})
            else:
                i += 1
        if i < len(tokens) and tokens[i].value == "}":
            i += 1
    while i < len(tokens) and tokens[i].value not in {"from", ";"}:
        i += 1
    if i < len(tokens) and tokens[i].value == "from":
        i += 1
        if i < len(tokens) and tokens[i].kind == "string":
            module = tokens[i].value[1:-1]
            i += 1
    if module is None:
        return None, max(i, start + 1)
    return {"kind": "import", "module": module, "names": names, "span": _span(tokens[start])}, i


def _class_record(tokens: list[Token], source: str, pairs: dict[int, int], start: int) -> tuple[dict[str, Any] | None, int]:
    i = start + 1
    if i >= len(tokens) or tokens[i].kind != "identifier":
        return None, start + 1
    name = tokens[i].value
    i += 1
    while i < len(tokens) and tokens[i].value != "{":
        i += 1
    if i >= len(tokens):
        return None, start + 1
    close = pairs.get(i)
    if close is None:
        return None, i + 1
    methods: list[dict[str, Any]] = []
    body = tokens[i + 1:close]
    body_pairs, _ = _match_pairs(body)
    j = 0
    while j < len(body):
        async_flag = body[j].value == "async"
        k = j + 1 if async_flag else j
        if k < len(body) and body[k].kind in {"identifier", "keyword"} and k + 1 < len(body) and body[k + 1].value == "(":
            method_name = body[k].value
            open_params = k + 1
            close_params = body_pairs.get(open_params)
            if close_params is not None and close_params + 1 < len(body) and body[close_params + 1].value == "{":
                body_open = close_params + 1
                body_close = body_pairs.get(body_open)
                if body_close is not None:
                    qualified = f"{name}.{method_name}"
                    method_body = body[body_open + 1:body_close]
                    methods.append({
                        "kind": "method",
                        "name": method_name,
                        "owner": name,
                        "qualified_name": qualified,
                        "async": async_flag,
                        "generator": False,
                        "parameters": _parameter_records(body[open_params + 1:close_params], source),
                        "returns_annotation": None,
                        "decorators": [],
                        "span": _span(body[j]),
                        "source": source[body[j].start:body[body_close].end],
                        "source_state": "active",
                        "decomposition_state": "not_decomposed",
                        "primitive_decomposition": {
                            "primitive_set_ref": "CW_LOGIC_PRIMITIVES",
                            "decomposition_state": "not_decomposed",
                            "body": [],
                            "unresolved": [{"reason": "JAVASCRIPT_PRIMITIVE_COMPILER_NOT_CONNECTED"}],
                            "canonical_ready": False,
                            "authority": "implementation_evidence",
                        },
                        "nested_functions": _extract_nested_functions(method_body, source, owner=qualified),
                        "logic": _logic_facts(method_body, source),
                    })
                    j = body_close + 1
                    continue
        j += 1
    return {"kind": "class", "name": name, "methods": methods, "span": _span(tokens[start])}, close + 1


def _export_records(tokens: list[Token], source: str, index: int) -> tuple[list[dict[str, Any]], int]:
    start = tokens[index]
    i = index + 1
    default = False
    if i < len(tokens) and tokens[i].value == "default":
        default = True
        i += 1
    if i < len(tokens) and tokens[i].value in {"async", "function"}:
        k = i + 1 if tokens[i].value == "async" else i
        if k < len(tokens) and tokens[k].value == "function":
            name_index = k + 1
            if name_index < len(tokens) and tokens[name_index].value == "*":
                name_index += 1
            name = tokens[name_index].value if name_index < len(tokens) and tokens[name_index].kind == "identifier" else "default"
            return [{
                "kind": "local_export",
                "exported_name": "default" if default else name,
                "local_name": name,
                "target_kind": "function",
                "target_qualified_name": name,
                "span": _span(start),
            }], i
    if i < len(tokens) and tokens[i].value == "class":
        name = tokens[i + 1].value if i + 1 < len(tokens) and tokens[i + 1].kind == "identifier" else "default"
        return [{"kind": "local_export", "exported_name": "default" if default else name, "local_name": name, "target_kind": "class", "target_qualified_name": name, "span": _span(start)}], i
    if not default and i < len(tokens) and tokens[i].value == "{":
        records: list[dict[str, Any]] = []
        i += 1
        while i < len(tokens) and tokens[i].value != "}":
            if tokens[i].kind in {"identifier", "keyword"}:
                local = tokens[i].value
                exported = local
                i += 1
                if i < len(tokens) and tokens[i].value == "as":
                    i += 1
                    if i < len(tokens) and tokens[i].kind in {"identifier", "keyword"}:
                        exported = tokens[i].value
                        i += 1
                records.append({"kind": "local_export", "exported_name": exported, "local_name": local, "target_kind": "reference", "target_qualified_name": local, "span": _span(start)})
            else:
                i += 1
        after = i + 1
        if after < len(tokens) and tokens[after].value == "from":
            module_index = after + 1
            module = tokens[module_index].value[1:-1] if module_index < len(tokens) and tokens[module_index].kind == "string" else None
            for record in records:
                record["kind"] = "re_export"
                record["source_module"] = module
                record["target_kind"] = "unresolved_re_export"
                record["target_qualified_name"] = None
            return records, module_index + 1
        return records, after
    if default and i < len(tokens) and tokens[i].kind == "identifier":
        name = tokens[i].value
        return [{"kind": "local_export", "exported_name": "default", "local_name": name, "target_kind": "reference", "target_qualified_name": name, "span": _span(start)}], i + 1
    return [], i


def extract_javascript(path: str, source: str) -> dict[str, Any]:
    raw_tokens, diagnostics = _lex(source)
    comments = [{"kind": "comment", "text": token.value, "span": _span(token)} for token in raw_tokens if token.kind == "comment"]
    tokens = _significant(raw_tokens)
    pairs, pair_diagnostics = _match_pairs(tokens)
    diagnostics.extend(pair_diagnostics)
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    exports: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    i = 0
    export_pending = False
    while i < len(tokens):
        token = tokens[i]
        if token.value == "import":
            record, next_index = _import_record(tokens, source, i)
            if record:
                imports.append(record)
            i = max(next_index, i + 1)
            continue
        if token.value == "export":
            records, next_index = _export_records(tokens, source, i)
            exports.extend(records)
            export_pending = True
            i += 1
            continue
        if token.value == "class":
            record, next_index = _class_record(tokens, source, pairs, i)
            if record:
                symbols.append(record)
                i = next_index
                export_pending = False
                continue
        if token.value == "function" or (token.value == "async" and i + 1 < len(tokens) and tokens[i + 1].value == "function"):
            record, next_index = _function_record(tokens, source, pairs, i)
            if record:
                symbols.append(record)
                i = next_index
                export_pending = False
                continue
        if token.value in {"const", "let", "var"} and i + 3 < len(tokens) and tokens[i + 1].kind == "identifier":
            name = tokens[i + 1].value
            eq = i + 2
            if tokens[eq].value == "=" and eq + 1 < len(tokens):
                start_expr = eq + 1
                paren = None
                if tokens[start_expr].value == "async":
                    start_expr += 1
                if start_expr < len(tokens) and tokens[start_expr].value == "(":
                    paren = start_expr
                elif start_expr < len(tokens) and tokens[start_expr].kind == "identifier" and start_expr + 1 < len(tokens) and tokens[start_expr + 1].value == "=>":
                    param_tokens = [tokens[start_expr]]
                    body_start = start_expr + 2
                    body_close = pairs.get(body_start) if body_start < len(tokens) and tokens[body_start].value == "{" else None
                    body_tokens = tokens[body_start + 1:body_close] if body_close is not None else tokens[body_start:body_start + 1]
                    symbols.append({
                        "kind": "function", "name": name, "owner": None, "qualified_name": name,
                        "async": tokens[eq + 1].value == "async", "generator": False,
                        "parameters": _parameter_records(param_tokens, source), "returns_annotation": None, "decorators": [],
                        "span": _span(token), "source": source[token.start:(tokens[body_close].end if body_close is not None else body_tokens[-1].end if body_tokens else token.end)],
                        "source_state": "active", "decomposition_state": "not_decomposed",
                        "primitive_decomposition": {"primitive_set_ref": "CW_LOGIC_PRIMITIVES", "decomposition_state": "not_decomposed", "body": [], "unresolved": [{"reason": "JAVASCRIPT_PRIMITIVE_COMPILER_NOT_CONNECTED"}], "canonical_ready": False, "authority": "implementation_evidence"},
                        "nested_functions": [], "logic": _logic_facts(body_tokens, source),
                    })
                    if export_pending:
                        exports.append({"kind": "local_export", "exported_name": name, "local_name": name, "target_kind": "function", "target_qualified_name": name, "span": _span(token)})
                    i = (body_close + 1) if body_close is not None else body_start + 1
                    export_pending = False
                    continue
                if paren is not None:
                    close_params = pairs.get(paren)
                    if close_params is not None and close_params + 1 < len(tokens) and tokens[close_params + 1].value == "=>":
                        body_start = close_params + 2
                        body_close = pairs.get(body_start) if body_start < len(tokens) and tokens[body_start].value == "{" else None
                        body_tokens = tokens[body_start + 1:body_close] if body_close is not None else tokens[body_start:body_start + 1]
                        symbols.append({
                            "kind": "function", "name": name, "owner": None, "qualified_name": name,
                            "async": tokens[eq + 1].value == "async", "generator": False,
                            "parameters": _parameter_records(tokens[paren + 1:close_params], source), "returns_annotation": None, "decorators": [],
                            "span": _span(token), "source": source[token.start:(tokens[body_close].end if body_close is not None else body_tokens[-1].end if body_tokens else token.end)],
                            "source_state": "active", "decomposition_state": "not_decomposed",
                            "primitive_decomposition": {"primitive_set_ref": "CW_LOGIC_PRIMITIVES", "decomposition_state": "not_decomposed", "body": [], "unresolved": [{"reason": "JAVASCRIPT_PRIMITIVE_COMPILER_NOT_CONNECTED"}], "canonical_ready": False, "authority": "implementation_evidence"},
                            "nested_functions": [], "logic": _logic_facts(body_tokens, source),
                        })
                        if export_pending:
                            exports.append({"kind": "local_export", "exported_name": name, "local_name": name, "target_kind": "function", "target_qualified_name": name, "span": _span(token)})
                        i = (body_close + 1) if body_close is not None else body_start + 1
                        export_pending = False
                        continue
        if token.value in {"with", "debugger"}:
            unsupported.append({"kind": "unsupported_syntax", "token": token.value, "span": _span(token)})
        i += 1

    # Fill export target kinds from extracted symbols where exact local identity is proven.
    function_names = {symbol.get("qualified_name") for symbol in symbols if symbol.get("kind") == "function"}
    for record in exports:
        target = record.get("target_qualified_name")
        if record.get("kind") == "local_export" and isinstance(target, str) and target in function_names:
            record["target_kind"] = "function"

    return {
        "language_id": "javascript",
        "parser_id": "cic-js-python-1",
        "parser_available": True,
        "diagnostics": diagnostics,
        "symbols": symbols,
        "imports": imports,
        "exports": exports,
        "evidence": [*comments, *unsupported],
        "javascript": {
            "token_count": len(tokens),
            "comments": comments,
            "unsupported": unsupported,
        },
    }
