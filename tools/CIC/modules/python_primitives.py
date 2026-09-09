from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PythonPrimitiveCompilation:
    function_name: str
    parameters: tuple[str, ...]
    primitive_set_ref: str
    body: tuple[dict[str, Any], ...]
    decomposition_state: str
    unresolved: tuple[dict[str, Any], ...]
    canonical_ready: bool


@dataclass(frozen=True)
class _Value:
    value: dict[str, Any]
    value_type: str | None


_COMPARE_OPS = {
    ast.Eq: "eq",
    ast.NotEq: "ne",
    ast.Lt: "lt",
    ast.LtE: "lte",
    ast.Gt: "gt",
    ast.GtE: "gte",
}


class _Compiler:
    def __init__(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.function = function
        self.locals: set[str] = set()
        self.types: dict[str, str | None] = {}
        self.unresolved: list[dict[str, Any]] = []
        for arg in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]:
            self.locals.add(arg.arg)
            annotation = ast.unparse(arg.annotation) if arg.annotation is not None else None
            self.types[arg.arg] = "bool" if annotation == "bool" else None
        if function.args.vararg:
            self.locals.add(function.args.vararg.arg)
            self.types[function.args.vararg.arg] = None
        if function.args.kwarg:
            self.locals.add(function.args.kwarg.arg)
            self.types[function.args.kwarg.arg] = None

    def _span(self, node: ast.AST) -> dict[str, int | None]:
        return {
            "line": getattr(node, "lineno", None),
            "column": getattr(node, "col_offset", None),
            "end_line": getattr(node, "end_lineno", None),
            "end_column": getattr(node, "end_col_offset", None),
        }

    def _reject(self, node: ast.AST, reason: str) -> None:
        self.unresolved.append({
            "kind": node.__class__.__name__,
            "reason": reason,
            "span": self._span(node),
        })

    def value(self, node: ast.AST) -> _Value | None:
        if isinstance(node, ast.Constant):
            value_type = "bool" if isinstance(node.value, bool) else type(node.value).__name__
            return _Value({"literal": node.value}, value_type)
        if isinstance(node, ast.Name):
            if node.id not in self.locals:
                self._reject(node, f"name {node.id!r} is not a proven function-local value")
                return None
            return _Value({"local_ref": node.id}, self.types.get(node.id))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = self.value(node.operand)
            if operand is None:
                return None
            return _Value({"op": "not", "arg": operand.value}, "bool")
        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or" if isinstance(node.op, ast.Or) else None
            if op is None:
                self._reject(node, "unsupported Python boolean operator")
                return None
            compiled = [self.value(item) for item in node.values]
            if any(item is None for item in compiled):
                return None
            values = [item for item in compiled if item is not None]
            if not all(item.value_type == "bool" for item in values):
                self._reject(
                    node,
                    "Python and/or returns operand values; CW boolean primitive is equivalent only for proven bool operands",
                )
                return None
            return _Value({"op": op, "args": [item.value for item in values]}, "bool")
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                self._reject(node, "chained Python comparison has no direct single CW comparison primitive")
                return None
            op = _COMPARE_OPS.get(type(node.ops[0]))
            if op is None:
                self._reject(node, f"comparison operator {node.ops[0].__class__.__name__} is outside CW_LOGIC_PRIMITIVES")
                return None
            left = self.value(node.left)
            right = self.value(node.comparators[0])
            if left is None or right is None:
                return None
            return _Value({"op": op, "left": left.value, "right": right.value}, "bool")
        self._reject(node, f"{node.__class__.__name__} has no semantics-preserving CW_LOGIC_PRIMITIVES mapping")
        return None

    def block(self, statements: list[ast.stmt]) -> tuple[list[dict[str, Any]], bool]:
        body: list[dict[str, Any]] = []
        complete = True
        for statement in statements:
            compiled = self.statement(statement)
            if compiled is None:
                complete = False
                continue
            body.append(compiled)
        return body, complete

    def statement(self, node: ast.stmt) -> dict[str, Any] | None:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                self._reject(node, "only one function-local Name assignment maps directly to assign")
                return None
            value = self.value(node.value)
            if value is None:
                return None
            name = node.targets[0].id
            self.locals.add(name)
            self.types[name] = value.value_type
            return {"op": "assign", "target": {"local_ref": name}, "value": value.value}
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or node.value is None:
                self._reject(node, "annotated assignment requires one local Name and explicit value")
                return None
            value = self.value(node.value)
            if value is None:
                return None
            name = node.target.id
            annotation = ast.unparse(node.annotation)
            self.locals.add(name)
            self.types[name] = "bool" if annotation == "bool" else value.value_type
            return {"op": "assign", "target": {"local_ref": name}, "value": value.value}
        if isinstance(node, ast.Return):
            if node.value is None:
                return {"op": "return"}
            value = self.value(node.value)
            return {"op": "return", "value": value.value} if value is not None else None
        if isinstance(node, ast.If):
            condition = self.value(node.test)
            if condition is None:
                return None
            if condition.value_type != "bool":
                self._reject(node.test, "if condition is not proven boolean")
                return None
            before_locals = set(self.locals)
            before_types = dict(self.types)
            then_body, then_complete = self.block(node.body)
            then_locals = set(self.locals)
            then_types = dict(self.types)
            self.locals = set(before_locals)
            self.types = dict(before_types)
            else_body, else_complete = self.block(node.orelse)
            else_locals = set(self.locals)
            else_types = dict(self.types)
            self.locals = before_locals | (then_locals & else_locals)
            for name in self.locals:
                if name in before_types:
                    self.types[name] = before_types[name]
                elif then_types.get(name) == else_types.get(name):
                    self.types[name] = then_types.get(name)
                else:
                    self.types[name] = None
            if not then_complete or not else_complete:
                self._reject(node, "if branch contains unresolved behavior; partial branch cannot be emitted as equivalent control logic")
                return None
            result: dict[str, Any] = {"op": "if", "condition": condition.value, "then": then_body}
            if node.orelse:
                result["else"] = else_body
            return result
        if isinstance(node, ast.While):
            condition = self.value(node.test)
            if condition is None:
                return None
            if condition.value_type != "bool":
                self._reject(node.test, "while condition is not proven boolean")
                return None
            before_locals = set(self.locals)
            before_types = dict(self.types)
            body, complete = self.block(node.body)
            body_types = dict(self.types)

            # A Python while may execute zero times. Therefore locals introduced
            # only inside the body are not definitely assigned after the loop.
            # Existing locals remain definitely present, but their proven type is
            # retained only when the body preserves the same type evidence.
            self.locals = set(before_locals)
            self.types = {
                name: before_types.get(name) if body_types.get(name) == before_types.get(name) else None
                for name in before_locals
            }

            if node.orelse:
                self._reject(node, "Python while-else has no direct CW while primitive semantics")
                return None
            if not complete:
                self._reject(node, "while body contains unresolved behavior")
                return None
            return {"op": "while", "condition": condition.value, "body": body}
        if isinstance(node, ast.Pass):
            self._reject(node, "pass has no operational primitive and is preserved as unresolved implementation evidence")
            return None
        self._reject(node, f"statement {node.__class__.__name__} is outside the proven compiler subset")
        return None


def _parameter_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    return tuple(arg.arg for arg in [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ])


def compile_python_function_node(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> PythonPrimitiveCompilation:
    """Compile one already-parsed Python function AST node.

    This is the importer-facing entry point. It preserves the parser's lexical
    node identity and avoids reparsing detached method/nested-function source.
    The result remains implementation evidence; `canonical_ready` is always
    false until canonical parameter/data/call bindings are established later.
    """
    parameters = _parameter_names(function)
    if isinstance(function, ast.AsyncFunctionDef):
        return PythonPrimitiveCompilation(
            function_name=function.name,
            parameters=parameters,
            primitive_set_ref="CW_LOGIC_PRIMITIVES",
            body=(),
            decomposition_state="none",
            unresolved=({
                "kind": "AsyncFunctionDef",
                "reason": "async execution is outside current equivalence harness",
            },),
            canonical_ready=False,
        )

    compiler = _Compiler(function)
    body, complete = compiler.block(function.body)
    state = "complete" if complete and not compiler.unresolved else "partial" if body else "none"
    return PythonPrimitiveCompilation(
        function_name=function.name,
        parameters=parameters,
        primitive_set_ref="CW_LOGIC_PRIMITIVES",
        body=tuple(body),
        decomposition_state=state,
        unresolved=tuple(compiler.unresolved),
        canonical_ready=False,
    )


def compile_python_function(source: str, function_name: str) -> PythonPrimitiveCompilation:
    """Compile one top-level fixture function through the node-level compiler."""
    tree = ast.parse(source, filename="<cic-equivalence>", type_comments=True)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one top-level function named {function_name!r}")
    return compile_python_function_node(matches[0])
