from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.context_rules import PatchPlan, Scaffold
from c_rust.render.scan import ClosePlan


@dataclass(frozen=True)
class SuffixResult:
    ok: bool
    suffix: str = ""
    notes: str = ""


def safe_boundary(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    return stripped[-1] in {";", "}"}


def create_plan(prefix: str, close_plan: ClosePlan) -> PatchPlan:
    return PatchPlan(
        prefix=prefix,
        scaffold=Scaffold(closers=close_plan.closers),
        brace_index=close_plan.brace_index,
        brace_order_to_close_idx=close_plan.brace_order_to_close_idx,
        tail_text=prefix,
    )


def plan_to_suffix(plan: PatchPlan) -> SuffixResult:
    return SuffixResult(ok=True, suffix=plan.render(), notes=",".join(plan.notes))
