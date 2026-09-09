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
    def __init__(self, *, locals=None, data=None, call_handlers=None, max_steps: int = 10_000) -> None:
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

    @staticmethod
    def _ref(value: Any, key: str, field: str) -> str:
        if not isinstance(value, dict) or set(value) != {key} or not isinstance(value.get(key), str) or not value[key]:
            raise LogicRuntimeError(f"{field} must use {{{key}: <non-empty string>}}")
        return value[key]

    def value(self, value: Any) -> Any:
        if not isinstance(value, dict):
            raise LogicRuntimeError(f"unsupported logic value: {value!r}")
        if set(value) == {"literal"}:
            return value["literal"]
        if set(value) == {"local_ref"}:
            name = self._ref(value, "local_ref", "logic value")
            if name not in self.locals:
                raise LogicRuntimeError(f"unassigned local_ref: {name}")
            return self.locals[name]
        if set(value) == {"ref"}:
            ref = self._ref(value, "ref", "logic value")
            if ref not in self.data:
                raise LogicRuntimeError(f"unresolved canonical data ref: {ref}")
            return self.data[ref]
        if "op" in value:
            return self.expression(value)
        raise LogicRuntimeError(f"unsupported logic value: {value!r}")

    def expression(self, expression: dict[str, Any]) -> Any:
        self._step()
        op = expression.get("op")
        if op == "read":
            return self.value(expression.get("source"))
        if op in {"and", "or", "xor"}:
            args = expression.get("args")
            if not isinstance(args, list) or len(args) < 2:
                raise LogicRuntimeError(f"{op}.args requires at least two values")
            values = [bool(self.value(item)) for item in args]
            return all(values) if op == "and" else any(values) if op == "or" else sum(values) % 2 == 1
        if op == "not":
            return not bool(self.value(expression.get("arg")))
        if op in {"eq", "ne", "lt", "lte", "gt", "gte"}:
            left, right = self.value(expression.get("left")), self.value(expression.get("right"))
            return {"eq": left == right, "ne": left != right, "lt": left < right, "lte": left <= right, "gt": left > right, "gte": left >= right}[op]
        raise LogicRuntimeError(f"unsupported expression op: {op!r}")

    def statement(self, statement: dict[str, Any]) -> None:
        self._step()
        op = statement.get("op")
        if op == "assign":
            self.locals[self._ref(statement.get("target"), "local_ref", "assign.target")] = self.value(statement.get("value")); return
        if op == "write":
            self.data[self._ref(statement.get("target"), "ref", "write.target")] = self.value(statement.get("value")); return
        if op == "call":
            ref = self._ref(statement.get("call_ref"), "ref", "call.call_ref"); self.calls.append(ref)
            handler = self.call_handlers.get(ref)
            if handler is None: raise LogicRuntimeError(f"no test call handler for: {ref}")
            handler(); return
        if op == "return":
            raise _ReturnSignal(self.value(statement["value"]) if "value" in statement else None)
        if op == "if":
            branch = statement.get("then") if bool(self.value(statement.get("condition"))) else statement.get("else", [])
            self.body(branch); return
        if op == "while":
            body = statement.get("body")
            if not isinstance(body, list): raise LogicRuntimeError("while.body must be an array")
            while bool(self.value(statement.get("condition"))): self._step(); self.body(body)
            return
        if op == "loop":
            body = statement.get("body")
            if not isinstance(body, list): raise LogicRuntimeError("loop.body must be an array")
            while True: self._step(); self.body(body)
        raise LogicRuntimeError(f"unsupported statement op: {op!r}")

    def body(self, body: Any) -> None:
        if not isinstance(body, list): raise LogicRuntimeError("logic body must be an array")
        for statement in body:
            if not isinstance(statement, dict): raise LogicRuntimeError("logic statement must be an object")
            self.statement(statement)

    def run(self, body: list[dict[str, Any]]) -> LogicExecutionResult:
        returned = False; value = None
        try: self.body(body)
        except _ReturnSignal as signal: returned = True; value = signal.value
        return LogicExecutionResult(returned, value, dict(self.locals), dict(self.data), tuple(self.calls), self.steps)


def execute_logic(body, *, locals=None, data=None, call_handlers=None, max_steps=10_000) -> LogicExecutionResult:
    return LogicRuntime(locals=locals, data=data, call_handlers=call_handlers, max_steps=max_steps).run(body)
