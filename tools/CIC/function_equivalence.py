from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from CIC.logic_runtime import LogicRuntimeError, execute_logic
from CIC.modules.python_primitives import compile_python_function


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


def _source_function(source: str, function_name: str):
    namespace: dict[str, Any] = {
        "__builtins__": {},
        "bool": bool,
        "int": int,
        "str": str,
        "float": float,
    }
    exec(compile(source, "<cic-equivalence-fixture>", "exec"), namespace, namespace)
    function = namespace.get(function_name)
    if not callable(function):
        raise ValueError(f"fixture did not define callable {function_name!r}")
    return function


def _run_source(function, args: dict[str, Any]) -> tuple[Any, str | None]:
    try:
        return function(**dict(args)), None
    except Exception as exc:  # fixture observation, not importer execution
        return None, f"{exc.__class__.__name__}:{exc}"


def _run_primitives(body: list[dict[str, Any]], args: dict[str, Any]) -> tuple[Any, str | None]:
    try:
        result = execute_logic(body, locals=args)
        return result.value if result.returned else None, None
    except LogicRuntimeError as exc:
        return None, f"{exc.__class__.__name__}:{exc}"
    except Exception as exc:
        return None, f"{exc.__class__.__name__}:{exc}"


def compare_python_fixture(
    source: str,
    function_name: str,
    vectors: list[dict[str, Any]],
    *,
    primitive_body_override: list[dict[str, Any]] | None = None,
) -> FunctionEquivalenceResult:
    """Differentially execute explicit test fixture source vs compiled primitives.

    This function is intentionally not used by CIC import/scan paths. Arbitrary
    user/repository source is never executed by normal static import analysis.
    `primitive_body_override` exists only for negative-control tests proving that
    semantic mutation is reported as MISMATCH.
    """
    compilation = compile_python_function(source, function_name)
    if compilation.decomposition_state != "complete":
        status = "PARTIALLY_DECOMPOSED" if compilation.decomposition_state == "partial" else "NOT_DECOMPOSED"
        return FunctionEquivalenceResult(
            status=status,
            decomposition_state=compilation.decomposition_state,
            observations=(),
            unresolved=compilation.unresolved,
        )

    function = _source_function(source, function_name)
    expected_params = set(compilation.parameters)
    primitive_body = list(compilation.body) if primitive_body_override is None else list(primitive_body_override)
    observations: list[FunctionObservation] = []
    for vector in vectors:
        if set(vector) != expected_params:
            raise ValueError(
                f"equivalence vector keys must match function parameters exactly: expected {sorted(expected_params)}, got {sorted(vector)}"
            )
        source_result, source_error = _run_source(function, vector)
        primitive_result, primitive_error = _run_primitives(primitive_body, vector)
        equivalent = (
            source_error == primitive_error
            and source_result == primitive_result
            and type(source_result) is type(primitive_result)
        )
        observations.append(FunctionObservation(
            args=dict(vector),
            source_result=source_result,
            primitive_result=primitive_result,
            source_error=source_error,
            primitive_error=primitive_error,
            equivalent=equivalent,
        ))

    return FunctionEquivalenceResult(
        status="EQUIVALENT" if all(item.equivalent for item in observations) else "MISMATCH",
        decomposition_state=compilation.decomposition_state,
        observations=tuple(observations),
        unresolved=compilation.unresolved,
    )
