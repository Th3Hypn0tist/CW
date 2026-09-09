from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SolverMode = Literal["off", "manual"]


@dataclass(frozen=True)
class SolverPolicy:
    mode: SolverMode = "off"
    token_budget: int = 0

    def __post_init__(self) -> None:
        if self.mode not in {"off", "manual"}:
            raise ValueError(f"unsupported CIC solver mode: {self.mode!r}")
        if not isinstance(self.token_budget, int) or self.token_budget < 0:
            raise ValueError("CIC solver token_budget must be a non-negative integer")
        if self.mode == "off" and self.token_budget != 0:
            raise ValueError("CIC solver OFF mode must have token_budget=0")
        if self.mode == "manual" and self.token_budget <= 0:
            raise ValueError("CIC solver manual mode requires an explicit positive token_budget")


@dataclass(frozen=True)
class SolverResult:
    ir: dict[str, Any]
    status: str
    mode: SolverMode
    token_budget: int
    tokens_used: int
    proposals: tuple[dict[str, Any], ...]
    canonical_changes: int
    placeholder: bool

    def report(self) -> dict[str, Any]:
        return {"status": self.status, "mode": self.mode, "token_budget": self.token_budget, "tokens_used": self.tokens_used, "proposal_count": len(self.proposals), "canonical_changes": self.canonical_changes, "placeholder": self.placeholder}


def run_solver(ir: dict[str, Any], *, policy: SolverPolicy | None = None) -> SolverResult:
    if not isinstance(ir, dict):
        raise TypeError("CIC solver input must be a Code IR object")
    selected = policy or SolverPolicy()
    status = "PASS_THROUGH_DISABLED" if selected.mode == "off" else "PASS_THROUGH_PLACEHOLDER"
    return SolverResult(ir=ir, status=status, mode=selected.mode, token_budget=selected.token_budget, tokens_used=0, proposals=(), canonical_changes=0, placeholder=True)
