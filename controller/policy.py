from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Literal

from controller.loop import ControllerOp, Policy, select_oracles_by_granularity
from core.budget import Budget
from core.interfaces import Oracle
from core.types import (
    Action,
    Artifact,
    FeedbackMode,
    Granularity,
    OracleOutput,
    RenderStatus,
    RollbackScope,
    StopReason,
    Verdict,
)


@dataclass(frozen=True)
class DefaultPolicyConfig:
    """Configuration knobs for DefaultPolicy behavior."""

    verify_on_boundary: bool = True
    verify_on_eos: bool = True
    boundary_granularity: Granularity = Granularity.STMT
    eos_granularity: Granularity = Granularity.PROGRAM
    enable_rollback: bool = True
    default_fail_scope: RollbackScope = RollbackScope.STMT
    enable_cdhr: bool = False
    enable_feedback: bool = True  # Controls both FEEDBACK and APPLY_PATCH.
    repair_verify_granularity: Granularity = Granularity.STMT
    commit_when_no_oracle_selected: bool = False
    terminate_on_eos_and_pass: bool = True
    max_repair_rounds: int | None = None
    oracle_selector: Literal["by_granularity"] = "by_granularity"
    feedback_mode: FeedbackMode = FeedbackMode.INLINE


class DefaultPolicy(Policy):
    """Full-feature DTV policy with ablation toggles.

    Invariants:
    - Never returns GENERATE/FEEDBACK when the token budget is exhausted.
    - Never returns VERIFY when can_verify is False (except after APPLY_PATCH).
    - Emits CONTINUE explicitly when verification is inconclusive.
    - EOS triggers a final VERIFY (typically PROGRAM) when enabled.
    - When EOS is reached, policy commits before terminating. If no oracles are selected at EOS,
      COMMIT is treated as acceptance of the final program.
    """

    def __init__(self, config: DefaultPolicyConfig | None = None) -> None:
        self.config = config or DefaultPolicyConfig()
        self._repair_rounds: dict[tuple[str, str], int] = {}

    def next_action(self, ctx) -> ControllerOp:
        tokens_left = _tokens_left(ctx.budget)
        is_eos = _is_eos(ctx.last_stop_reason)
        is_boundary = _is_boundary_suffix(ctx.state.prefix)
        can_verify = _can_verify(self.config, is_boundary, is_eos)

        if self.config.enable_feedback:
            if ctx.pending_patch is not None and ctx.repair_base_prefix is not None:
                return ControllerOp(Action.APPLY_PATCH)
            if ctx.last_action == Action.APPLY_PATCH:
                return ControllerOp(Action.VERIFY, granularity=self.config.repair_verify_granularity)
            if (
                ctx.failed_prefix is not None
                and ctx.repair_base_prefix is not None
                and ctx.pending_patch is None
            ):
                if tokens_left <= 0:
                    return ControllerOp(Action.TERMINATE)
                if not _can_start_repair(self.config, self._repair_rounds, ctx):
                    return ControllerOp(Action.GENERATE)
                _record_repair_round(self._repair_rounds, ctx)
                return ControllerOp(Action.FEEDBACK, feedback_mode=self.config.feedback_mode)

        if ctx.last_action is None:
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.GENERATE:
            if tokens_left <= 0:
                if can_verify:
                    return ControllerOp(Action.VERIFY, granularity=_select_verify_granularity(self.config, is_eos))
                return ControllerOp(Action.TERMINATE)
            if can_verify:
                return ControllerOp(Action.VERIFY, granularity=_select_verify_granularity(self.config, is_eos))
            return ControllerOp(Action.GENERATE)

        if ctx.last_action == Action.VERIFY:
            if ctx.last_render_status != RenderStatus.OK:
                return _continue_or_terminate(tokens_left)
            if not ctx.last_outputs:
                if is_eos:
                    return ControllerOp(Action.COMMIT)
                if self.config.commit_when_no_oracle_selected:
                    return ControllerOp(Action.COMMIT)
                return _continue_or_terminate(tokens_left)
            if _any_fail(ctx.last_outputs):
                if self.config.enable_rollback:
                    scope = _select_fail_scope(self.config, ctx.last_outputs)
                    return ControllerOp(Action.ROLLBACK, rollback_scope=scope)
                return _continue_or_terminate(tokens_left)
            if _all_pass(ctx.last_outputs):
                return ControllerOp(Action.COMMIT)
            return _continue_or_terminate(tokens_left)

        if ctx.last_action == Action.CONTINUE:
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.COMMIT:
            if (
                self.config.terminate_on_eos_and_pass
                and is_eos
                and (not ctx.last_outputs or _all_pass(ctx.last_outputs))
            ):
                return ControllerOp(Action.TERMINATE)
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.ROLLBACK:
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.TERMINATE:
            return ControllerOp(Action.TERMINATE)

        return ControllerOp(Action.TERMINATE)

    def select_oracles(
        self,
        artifact: Artifact,
        budget: Budget,
        available: Sequence[Oracle],
    ) -> list[Oracle]:
        if self.config.oracle_selector == "by_granularity":
            return select_oracles_by_granularity(artifact, budget, available)
        return select_oracles_by_granularity(artifact, budget, available)


def _tokens_left(budget: Budget) -> int:
    return max(0, budget.gen_tokens_budget - budget.gen_tokens_used)


def _is_boundary_suffix(prefix: str) -> bool:
    return prefix.rstrip().endswith((";", "}"))


def _is_eos(stop_reason: StopReason | None) -> bool:
    return stop_reason is not None and stop_reason.kind == "eos"


def _can_verify(config: DefaultPolicyConfig, is_boundary: bool, is_eos: bool) -> bool:
    return (config.verify_on_boundary and is_boundary) or (config.verify_on_eos and is_eos)


def _select_verify_granularity(config: DefaultPolicyConfig, is_eos: bool) -> Granularity:
    return config.eos_granularity if is_eos else config.boundary_granularity


def _generate_or_terminate(tokens_left: int) -> ControllerOp:
    if tokens_left > 0:
        return ControllerOp(Action.GENERATE)
    return ControllerOp(Action.TERMINATE)


def _continue_or_terminate(tokens_left: int) -> ControllerOp:
    if tokens_left > 0:
        return ControllerOp(Action.CONTINUE)
    return ControllerOp(Action.TERMINATE)


def _any_fail(outputs: tuple[OracleOutput, ...]) -> bool:
    return any(output.verdict == Verdict.FAIL for output in outputs)


def _all_pass(outputs: tuple[OracleOutput, ...]) -> bool:
    return all(output.verdict == Verdict.PASS for output in outputs)


def _select_fail_scope(config: DefaultPolicyConfig, outputs: tuple[OracleOutput, ...]) -> RollbackScope:
    if config.enable_cdhr:
        for output in outputs:
            for diag in output.diagnostics:
                if diag.hint_scope is not None:
                    return diag.hint_scope
    return config.default_fail_scope


def _repair_key(ctx) -> tuple[str, str] | None:
    if ctx.failed_prefix is None or ctx.repair_base_prefix is None:
        return None
    return (ctx.repair_base_prefix, ctx.failed_prefix)


def _can_start_repair(
    config: DefaultPolicyConfig,
    rounds: dict[tuple[str, str], int],
    ctx,
) -> bool:
    if not config.enable_feedback:
        return False
    if config.max_repair_rounds is None:
        return True
    key = _repair_key(ctx)
    if key is None:
        return False
    return rounds.get(key, 0) < config.max_repair_rounds


def _record_repair_round(rounds: dict[tuple[str, str], int], ctx) -> None:
    key = _repair_key(ctx)
    if key is None:
        return
    rounds[key] = rounds.get(key, 0) + 1
