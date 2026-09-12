from __future__ import annotations

import ast
from typing import Any


class PythonRegistrationError(ValueError):
    pass


def _span(node: ast.AST) -> dict[str, int | None]:
    return {
        "line": getattr(node, "lineno", None),
        "column": getattr(node, "col_offset", None),
        "end_line": getattr(node, "end_lineno", None),
        "end_column": getattr(node, "end_col_offset", None),
    }


def _name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _top_level_constants(tree: ast.Module) -> dict[str, Any]:
    constants: dict[str, Any] = {}
    for node in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Constant):
            continue
        if isinstance(value.value, (str, int, float, bool, type(None))):
            constants[target.id] = value.value
    return constants


def _binding(node: ast.AST, constants: dict[str, Any]) -> dict[str, Any]:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return {"kind": "literal", "value": node.value}
    if isinstance(node, ast.Name):
        if node.id in constants:
            return {"kind": "constant_ref", "symbol": node.id, "value": constants[node.id]}
        return {"kind": "symbol_ref", "symbol": node.id}
    name = _name(node)
    if isinstance(name, str) and name:
        return {"kind": "symbol_ref", "symbol": name}
    try:
        expression = ast.unparse(node)
    except Exception:
        expression = node.__class__.__name__
    return {"kind": "expression", "expression": expression}


def extract_python_registrations(path: str, source: str) -> list[dict[str, Any]]:
    """Extract explicit factory-return registration evidence without assigning semantics.

    A record is emitted only when a top-level function directly returns a constructor
    call. Keyword bindings preserve whether a value is a literal, a top-level
    constant reference, a symbol reference, or an unresolved expression.
    """
    try:
        tree = ast.parse(source, filename=path, type_comments=True)
    except SyntaxError:
        return []

    constants = _top_level_constants(tree)
    records: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
                continue
            call = statement.value
            constructor = _name(call.func)
            if not isinstance(constructor, str) or not constructor:
                continue
            keywords: dict[str, dict[str, Any]] = {}
            for keyword in call.keywords:
                if keyword.arg is None:
                    continue
                keywords[keyword.arg] = _binding(keyword.value, constants)
            records.append({
                "kind": "returned_constructor",
                "factory_function": node.name,
                "constructor": constructor,
                "keywords": keywords,
                "positional_args": [_binding(arg, constants) for arg in call.args],
                "span": _span(statement),
                "canonical_semantic_authority": False,
            })
    return records
