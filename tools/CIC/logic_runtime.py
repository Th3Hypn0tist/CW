from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class LogicRuntimeError(ValueError):
    pass


@dataclass(frozen=True)
class LogicExecutionResult:
    returned: bool
    value: Any
    locals: dict[str, Any]
    data: dict[str, Any]
    calls: tuple[str, ...]
    steps: int


class _ReturnSignal(Exception):
    def __init__(self, value: Any):
        super().__init__()
        self.value = value


class LogicRuntime:
    """Deterministic executor for the locked CW_LOGIC_PRIMITIVES vocabulary.

    This runtime is a conformance-test harness. It does not claim external
    implementation correspondence and is not invoked by normal CIC corpus scans.
    """

    def __init__(
        self,
        *,
        locals: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        call_handlers: dict[str, Callable[[], Any]] | None = None,
        max_steps: int = 10_000,
    ) -> None:
        self.locals = dict(locals or {})
        self.data = dict(data or {})
        self.call_handlers = dict(call_handlers or {})
        self.max_steps = max_steps
        self.steps = 0
        self.calls: list[str] = []

    def _step(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise LogicRuntimeError(f"logic execution exceeded max_steps={self.max_steps}")

    def _canonical_ref(self, value: Any, field: str) -> str:
        if not isinstance(value, dict) or set(value) != {"ref"}:
            raise LogicRuntimeError(f"{field} must be canonical_ref form")
        ref = value["ref"]
        if not isinstance(ref, str) or not ref:
            raise LogicRuntimeError(f"{field}.ref must be non-empty")
        return ref

    def _local_ref(self, value: Any, field: str) -> str:
        if not isinstance(value, dict) or set(value) != {"local_ref"}:
            raise LogicRuntimeError(f"{field} must be local_ref form")
        ref = value["local_ref"]
        if not isinstance(ref, str) or not ref:
            raise LogicRuntimeError(f"{field}.local_ref must be non-empty")
        return ref

    def value(self, value: Any) -> Any:
        if isinstance(value, dict):
            if set(value) == {"literal"}:
                return value["literal"]
            if set(value) == {"local_ref"}:
                name = self._local_ref(value, "logic value")
                if name not in self.locals:
                    raise LogicRuntimeError(f"unassigned local_ref: {name}")
                return self.locals[name]
            if set(value) == {"ref"}:
                ref = self._canonical_ref(value, "logic value")
                if ref not in self.data:
                    raise LogicRuntimeError(f"unresolved canonical data ref: {ref}")
                return self.data[ref]
            if "op" in value:
                return self.expression(value)
        raise LogicRuntimeError(f"unsupported logic value: {value!r}")

    def expression(self, expression: Any) -> Any:
        if not isinstance(expression, dict):
            raise LogicRuntimeError("logic expression must be an object")
        self._step()
        op = expression.get("op")
        if op == "read":
            return self.value(expression.get("source"))
        if op in {"and", "or", "xor"}:
            args = expression.get("args")
            if not isinstance(args, list) or len(args) < 2:
                raise LogicRuntimeError(f"{op}.args requires at least two values")
            values = [bool(self.value(item)) for item in args]
            if op == "and":
                return all(values)
            if op == "or":
                return any(values)
            return sum(1 for item in values if item) % 2 == 1
        if op == "not":
            return not bool(self.value(expression.get("arg")))
        if op in {"eq", "ne", "lt", "lte", "gt", "gte"}:
            left = self.value(expression.get("left"))
            right = self.value(expression.get("right"))
            if op == "eq":
                return left == right
            if op == "ne":
                return left != right
            if op == "lt":
                return left < right
            if op == "lte":
                return left <= right
            if op == "gt":
                return left > right
            return left >= right
        raise LogicRuntimeError(f"unsupported expression op: {op!r}")

    def statement(self, statement: Any) -> None:
        if not isinstance(statement, dict):
            raise LogicRuntimeError("logic statement must be an object")
        self._step()
        op = statement.get("op")
        if op == "assign":
            target = self._local_ref(statement.get("target"), "assign.target")
            self.locals[target] = self.value(statement.get("value"))
            return
        if op == "write":
            target = self._canonical_ref(statement.get("target"), "write.target")
            self.data[target] = self.value(statement.get("value"))
            return
        if op == "call":
            call_ref = self._canonical_ref(statement.get("call_ref"), "call.call_ref")
            self.calls.append(call_ref)
            handler = self.call_handlers.get(call_ref)
            if handler is None:
                raise LogicRuntimeError(f"no test call handler for: {call_ref}")
            handler()
            return
        if op == "return":
            value = self.value(statement["value"]) if "value" in statement else None
            raise _ReturnSignal(value)
        if op == "if":
            branch = statement.get("then") if bool(self.value(statement.get("condition"))) else statement.get("else", [])
            if not isinstance(branch, list):
                raise LogicRuntimeError("if branch must be an array")
            self.body(branch)
            return
        if op == "while":
            body = statement.get("body")
            if not isinstance(body, list):
                raise LogicRuntimeError("while.body must be an array")
            while bool(self.value(statement.get("condition"))):
                self._step()
                self.body(body)
            return
        if op == "loop":
            body = statement.get("body")
            if not isinstance(body, list):
                raise LogicRuntimeError("loop.body must be an array")
            while True:
                self._step()
                self.body(body)
        raise LogicRuntimeError(f"unsupported statement op: {op!r}")

    def body(self, body: Any) -> None:
        if not isinstance(body, list):
            raise LogicRuntimeError("logic body must be an array")
        for statement in body:
            self.statement(statement)

    def run(self, body: list[dict[str, Any]]) -> LogicExecutionResult:
        returned = False
        value = None
        try:
            self.body(body)
        except _ReturnSignal as signal:
            returned = True
            value = signal.value
        return LogicExecutionResult(
            returned=returned,
            value=value,
            locals=dict(self.locals),
            data=dict(self.data),
            calls=tuple(self.calls),
            steps=self.steps,
        )


def execute_logic(
    body: list[dict[str, Any]],
    *,
    locals: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    call_handlers: dict[str, Callable[[], Any]] | None = None,
    max_steps: int = 10_000,
) -> LogicExecutionResult:
    return LogicRuntime(
        locals=locals,
        data=data,
        call_handlers=call_handlers,
        max_steps=max_steps,
    ).run(body)
