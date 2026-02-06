from __future__ import annotations

from c_rust.render.context_rules.base import (
    Analysis,
    ContextRule,
    ContextRegistry,
    PatchPhase,
    PatchPlan,
    Scaffold,
    ancestor_of_type,
    ancestor_chain_of_type,
    block_tail_needs_todo,
    has_else_clause,
)
from c_rust.render.context_rules.if_rule import IfContext, IfContextRule
from c_rust.render.context_rules.let_rule import LetContext, LetContextRule
from c_rust.render.context_rules.match_rule import MatchContext, MatchContextRule
from c_rust.render.context_rules.function_rule import FunctionContext, FunctionContextRule
from c_rust.render.context_rules.match_arm_witness_rule import (
    MatchArmTypeWitnessContext,
    MatchArmTypeWitnessRule,
)


CONTEXT_RULES: tuple[ContextRule, ...] = (
    IfContextRule(),
    MatchContextRule(),
    MatchArmTypeWitnessRule(),
    LetContextRule(),
    FunctionContextRule(),
)


def apply_patch_rules(
    plan: PatchPlan,
    analysis: Analysis,
    *,
    keys: tuple[str, ...] | None = None,
    phases: tuple[PatchPhase, ...] | None = None,
) -> None:
    for rule in CONTEXT_RULES:
        if keys is not None and rule.key not in keys:
            continue
        if phases is not None and rule.phase not in phases:
            continue
        rule.apply_patch(plan, analysis)


__all__ = [
    "Analysis",
    "ContextRule",
    "ContextRegistry",
    "FunctionContext",
    "FunctionContextRule",
    "IfContext",
    "IfContextRule",
    "LetContext",
    "LetContextRule",
    "MatchArmTypeWitnessContext",
    "MatchArmTypeWitnessRule",
    "MatchContext",
    "MatchContextRule",
    "PatchPhase",
    "PatchPlan",
    "Scaffold",
    "CONTEXT_RULES",
    "apply_patch_rules",
    "ancestor_of_type",
    "ancestor_chain_of_type",
    "block_tail_needs_todo",
    "has_else_clause",
]
