from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .logic_runtime import LogicRuntimeError, execute_logic
from .modules.python_primitives import compile_python_function


@dataclass(frozen=True)
class FunctionObservation:
    args: dict[str, Any]
    source_result: Any
    primitive_result: Any
    source_error: str | None
    primitive_error: str | None
    equivalent: bool


@dataclass(frozen=True)
class FunctionEquivalenceResult:
    status: str
    decomposition_state: str
    observations: tuple[FunctionObservation, ...]
    unresolved: tuple[dict[str, Any], ...]


def compare_python_fixture(source: str, function_name: str, vectors: list[dict[str, Any]], *, primitive_body_override=None) -> FunctionEquivalenceResult:
    compilation = compile_python_function(source, function_name)
    if compilation.decomposition_state != "complete":
        status = "PARTIALLY_DECOMPOSED" if compilation.decomposition_state == "partial" else "NOT_DECOMPOSED"
        return FunctionEquivalenceResult(status, compilation.decomposition_state, (), compilation.unresolved)
    namespace: dict[str, Any] = {"__builtins__": {}, "bool": bool, "int": int, "str": str, "float": float}
    exec(compile(source, "<cic-equivalence-fixture>", "exec"), namespace, namespace)
    function = namespace.get(function_name)
    if not callable(function): raise ValueError(f"fixture did not define callable {function_name!r}")
    expected = set(compilation.parameters); body = list(compilation.body) if primitive_body_override is None else list(primitive_body_override); observations=[]
    for vector in vectors:
        if set(vector) != expected: raise ValueError(f"equivalence vector keys must match parameters: {sorted(expected)}")
        try: source_result=function(**dict(vector)); source_error=None
        except Exception as exc: source_result=None; source_error=f"{exc.__class__.__name__}:{exc}"
        try:
            primitive=execute_logic(body,locals=vector); primitive_result=primitive.value if primitive.returned else None; primitive_error=None
        except (LogicRuntimeError,Exception) as exc: primitive_result=None; primitive_error=f"{exc.__class__.__name__}:{exc}"
        equivalent=source_error==primitive_error and source_result==primitive_result and type(source_result) is type(primitive_result)
        observations.append(FunctionObservation(dict(vector),source_result,primitive_result,source_error,primitive_error,equivalent))
    return FunctionEquivalenceResult("EQUIVALENT" if all(item.equivalent for item in observations) else "MISMATCH",compilation.decomposition_state,tuple(observations),compilation.unresolved)
