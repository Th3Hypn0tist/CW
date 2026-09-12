from __future__ import annotations

import ast
from typing import Any

from CIC.modules.python_primitives import compile_python_function_node


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
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Subscript):
        base = _name(node.value)
        return f"{base}[...]" if base else None
    return None


def _literal_value(node: ast.AST | None) -> tuple[bool, Any]:
    if node is None:
        return False, None
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return True, node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[Any] = []
        for item in node.elts:
            ok, value = _literal_value(item)
            if not ok:
                return False, None
            values.append(value)
        if isinstance(node, ast.Set):
            values = sorted(values, key=lambda item: repr(item))
        return True, values
    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key_node, value_node in zip(node.keys, node.values):
            ok_key, key = _literal_value(key_node)
            ok_value, value = _literal_value(value_node)
            if not ok_key or not ok_value or not isinstance(key, str):
                return False, None
            result[key] = value
        return True, result
    return False, None


def _operator(node: ast.AST) -> str:
    return node.__class__.__name__


class _FunctionFacts(ast.NodeVisitor):
    """Collect observable facts from one lexical function scope only."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.reads: list[dict[str, Any]] = []
        self.writes: list[dict[str, Any]] = []
        self.assignments: list[dict[str, Any]] = []
        self.operators: list[dict[str, Any]] = []
        self.comparisons: list[dict[str, Any]] = []
        self.branches: list[dict[str, Any]] = []
        self.loops: list[dict[str, Any]] = []
        self.returns: list[dict[str, Any]] = []
        self.raises: list[dict[str, Any]] = []
        self.awaits: list[dict[str, Any]] = []
        self.yields: list[dict[str, Any]] = []
        self.lambdas: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return None

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.lambdas.append({"span": _span(node)})
        return None

    def visit_Name(self, node: ast.Name) -> None:
        fact = {"name": node.id, "span": _span(node)}
        if isinstance(node.ctx, ast.Load):
            self.reads.append(fact)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self.writes.append(fact)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append({
            "target": _name(node.func),
            "args": len(node.args),
            "kwargs": [kw.arg for kw in node.keywords],
            "span": _span(node),
        })
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.assignments.append({"targets": [_name(target) for target in node.targets], "span": _span(node)})
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.assignments.append({"targets": [_name(node.target)], "annotated": True, "span": _span(node)})
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.assignments.append({"targets": [_name(node.target)], "augmented": _operator(node.op), "span": _span(node)})
        self.operators.append({"operator": _operator(node.op), "span": _span(node)})
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self.operators.append({"operator": _operator(node.op), "span": _span(node)})
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.operators.append({"operator": _operator(node.op), "span": _span(node)})
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        self.operators.append({"operator": _operator(node.op), "span": _span(node)})
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        self.comparisons.append({"operators": [_operator(op) for op in node.ops], "span": _span(node)})
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.branches.append({"kind": "if", "span": _span(node)})
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.branches.append({"kind": "if_expression", "span": _span(node)})
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.branches.append({"kind": "match", "cases": len(node.cases), "span": _span(node)})
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.loops.append({"kind": "for", "span": _span(node)})
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.loops.append({"kind": "async_for", "span": _span(node)})
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.loops.append({"kind": "while", "span": _span(node)})
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        self.returns.append({"value": _name(node.value), "span": _span(node)})
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.raises.append({"exception": _name(node.exc), "span": _span(node)})
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        self.awaits.append({"target": _name(node.value), "span": _span(node)})
        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield) -> None:
        self.yields.append({"value": _name(node.value), "span": _span(node)})
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        self.yields.append({"value": _name(node.value), "from": True, "span": _span(node)})
        self.generic_visit(node)


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    defaults_offset = len(positional) - len(args.defaults)
    result: list[dict[str, Any]] = []
    for index, arg in enumerate(positional):
        result.append({
            "name": arg.arg,
            "kind": "positional_only" if index < len(args.posonlyargs) else "positional",
            "annotation": ast.unparse(arg.annotation) if arg.annotation is not None else None,
            "has_default": index >= defaults_offset,
            "span": _span(arg),
        })
    if args.vararg:
        result.append({"name": args.vararg.arg, "kind": "vararg", "annotation": ast.unparse(args.vararg.annotation) if args.vararg.annotation else None, "span": _span(args.vararg)})
    for index, arg in enumerate(args.kwonlyargs):
        result.append({
            "name": arg.arg,
            "kind": "keyword_only",
            "annotation": ast.unparse(arg.annotation) if arg.annotation is not None else None,
            "has_default": args.kw_defaults[index] is not None,
            "span": _span(arg),
        })
    if args.kwarg:
        result.append({"name": args.kwarg.arg, "kind": "kwarg", "annotation": ast.unparse(args.kwarg.annotation) if args.kwarg.annotation else None, "span": _span(args.kwarg)})
    return result


def _nested_functions(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str, scope: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nested_scope = f"{scope}.<locals>"
            result.append(_function_record(statement, source, owner=nested_scope))
    return result


def _primitive_evidence(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    compilation = compile_python_function_node(node)
    return {
        "primitive_set_ref": compilation.primitive_set_ref,
        "decomposition_state": compilation.decomposition_state,
        "body": list(compilation.body),
        "unresolved": list(compilation.unresolved),
        "canonical_ready": compilation.canonical_ready,
        "authority": "implementation_evidence",
    }


def _function_record(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str, *, owner: str | None = None) -> dict[str, Any]:
    facts = _FunctionFacts()
    for statement in node.body:
        facts.visit(statement)
    exact_source = ast.get_source_segment(source, node)
    scoped_name = f"{owner}.{node.name}" if owner else node.name
    primitive_decomposition = _primitive_evidence(node)
    decomposition_state = primitive_decomposition["decomposition_state"]
    return {
        "kind": "method" if owner and ".<locals>" not in owner else "function",
        "name": node.name,
        "owner": owner,
        "qualified_name": scoped_name,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "parameters": _parameters(node),
        "returns_annotation": ast.unparse(node.returns) if node.returns is not None else None,
        "decorators": [ast.unparse(item) for item in node.decorator_list],
        "span": _span(node),
        "source": exact_source,
        "source_state": "archived" if decomposition_state == "complete" else "active",
        "decomposition_state": decomposition_state,
        "primitive_decomposition": primitive_decomposition,
        "nested_functions": _nested_functions(node, source, scoped_name),
        "logic": {
            "calls": facts.calls,
            "reads": facts.reads,
            "writes": facts.writes,
            "assignments": facts.assignments,
            "operators": facts.operators,
            "comparisons": facts.comparisons,
            "branches": facts.branches,
            "loops": facts.loops,
            "returns": facts.returns,
            "raises": facts.raises,
            "awaits": facts.awaits,
            "yields": facts.yields,
            "lambdas": facts.lambdas,
        },
    }


def extract_python(path: str, source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source, filename=path, type_comments=True)
    except SyntaxError as exc:
        return {
            "language_id": "python",
            "parser_id": "python",
            "parser_available": True,
            "diagnostics": [{"code": "SYNTAX_ERROR", "message": exc.msg, "line": exc.lineno, "column": exc.offset}],
            "symbols": [],
            "imports": [],
            "evidence": [],
        }

    imports: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"kind": "import", "module": alias.name, "alias": alias.asname, "span": _span(node)})
        elif isinstance(node, ast.ImportFrom):
            imports.append({
                "kind": "from_import",
                "module": node.module,
                "level": node.level,
                "names": [{"name": alias.name, "alias": alias.asname} for alias in node.names],
                "span": _span(node),
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_function_record(node, source))
        elif isinstance(node, ast.ClassDef):
            methods = [
                _function_record(child, source, owner=node.name)
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            symbols.append({
                "kind": "class",
                "name": node.name,
                "bases": [ast.unparse(base) for base in node.bases],
                "decorators": [ast.unparse(item) for item in node.decorator_list],
                "methods": methods,
                "span": _span(node),
            })
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            record: dict[str, Any] = {
                "kind": "variable",
                "names": [_name(target) for target in targets],
                "annotation": ast.unparse(node.annotation) if isinstance(node, ast.AnnAssign) and node.annotation is not None else None,
                "span": _span(node),
            }
            value_node = node.value
            ok, literal_value = _literal_value(value_node)
            if ok:
                record["literal_value"] = literal_value
            symbols.append(record)
        else:
            evidence.append({"kind": node.__class__.__name__, "span": _span(node)})

    return {
        "language_id": "python",
        "parser_id": "python",
        "parser_available": True,
        "diagnostics": [],
        "symbols": symbols,
        "imports": imports,
        "evidence": evidence,
    }
