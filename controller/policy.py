from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from controller.loop import ControllerOp, Policy, select_oracles_by_granularity
from core.budget import Budget
from core.interfaces import Oracle
from core.types import (
    Action,
    Artifact,
    FeedbackMechanism,
    Granularity,
    OracleOutput,
    RenderStatus,
    StopReason,
    Verdict,
)


@dataclass(frozen=True)
class DefaultPolicyConfig:
    """Configuration knobs for DefaultPolicy behavior."""

    verify_on_boundary: bool = True
    verify_on_close: bool = True
    boundary_granularity: Granularity = Granularity.STMT
    close_granularity: Granularity = Granularity.FUNC
    enable_rollback: bool = True
    default_fail_scope: Granularity = Granularity.STMT
    stmt_stall_max_retries_before_escalation: int = 3
    enable_cdhr: bool = False
    enable_feedback: bool = True  # Controls both FEEDBACK and APPLY_PATCH.
    repair_verify_granularity: Granularity = Granularity.STMT
    commit_when_no_oracle_selected: bool = False
    max_repair_rounds: int | None = None
    feedback_default_mechanism: FeedbackMechanism = FeedbackMechanism.A
    feedback_force_mechanism: FeedbackMechanism | None = None
    feedback_scope_escalation: Granularity = Granularity.FUNC
    feedback_error_escalation_threshold: int = 3
    feedback_max_a_rounds_per_key: int = 2
    feedback_max_b_rounds_per_key: int | None = None
    feedback_max_b_no_patch_rounds: int = 3
    feedback_budget_reserve_tokens: int = 0
    feedback_min_tokens_a: int = 0
    feedback_min_tokens_b: int = 0


@dataclass
class _RepairScheduleState:
    a_rounds: int = 0
    b_rounds: int = 0
    last_fail_scope: Granularity | None = None
    last_error_count: int = 0
    locked_mechanism: FeedbackMechanism | None = None
    b_no_patch_rounds: int = 0


@dataclass(frozen=True)
class _FailSnapshot:
    failed_prefix: str
    scope: Granularity
    error_count: int


class DefaultPolicy(Policy):
    """Full-feature DTV policy with ablation toggles.

    Invariants:
    - Never returns GENERATE/FEEDBACK when the token budget is exhausted.
    - Never returns VERIFY when can_verify is False (except after APPLY_PATCH).
    - Emits CONTINUE explicitly when verification is inconclusive.
    - Candidate closure triggers a final intra-candidate VERIFY when enabled.
    - Once a candidate closes, DTV never reopens it; any final acceptance is external.
    """

    def __init__(self, config: DefaultPolicyConfig | None = None) -> None:
        self.config = config or DefaultPolicyConfig()
        self._repair_rounds: dict[tuple[str, Granularity], int] = {}
        self._repair_schedule: dict[tuple[str, Granularity], _RepairScheduleState] = {}
        self._pending_fail_snapshot: _FailSnapshot | None = None
        self._stmt_stall_key: tuple[str, tuple[Granularity, ...]] | None = None
        self._stmt_stall_retries: int = 0

    def next_action(self, ctx) -> ControllerOp:
        tokens_left = _tokens_left(ctx.budget)
        is_closed = _is_write_region_closed(ctx.last_stop_reason)
        is_boundary = _is_boundary_suffix(ctx.state.prefix)
        can_verify = _can_verify(self.config, is_boundary, is_closed)

        if self.config.enable_feedback:
            if ctx.pending_patch is not None and ctx.repair_base_prefix is not None:
                return ControllerOp(Action.APPLY_PATCH)
            if ctx.last_action == Action.APPLY_PATCH:
                return ControllerOp(
                    Action.VERIFY,
                    verification_granularity=self.config.repair_verify_granularity,
                )
            if (
                ctx.failed_prefix is not None
                and ctx.repair_base_prefix is not None
                and ctx.pending_patch is None
                and ctx.last_action != Action.VERIFY
            ):
                key = _repair_key(ctx)
                if key is not None:
                    schedule_state = self._repair_schedule.setdefault(key, _RepairScheduleState())
                    self._apply_pending_fail_snapshot(schedule_state, ctx)
                else:
                    schedule_state = _RepairScheduleState()
                # Track B rounds that produced no usable patch
                # (parser extraction or scope validation failed).
                if ctx.last_action == Action.FEEDBACK:
                    schedule_state.b_no_patch_rounds += 1
                    if (
                        schedule_state.b_no_patch_rounds
                        >= self.config.feedback_max_b_no_patch_rounds
                    ):
                        # Treat as a verify fail: rollback with stall escalation.
                        scope = self._select_fail_scope(ctx)
                        return ControllerOp(Action.ROLLBACK, rollback_scope=scope)
                if tokens_left <= 0:
                    return ControllerOp(Action.TERMINATE)
                if not _can_start_repair(self.config, self._repair_rounds, ctx):
                    return ControllerOp(Action.GENERATE)
                mechanism = self._choose_feedback_mechanism(schedule_state, tokens_left)
                if mechanism is None:
                    return ControllerOp(Action.TERMINATE)
                _record_repair_round(self._repair_rounds, ctx)
                self._record_mechanism_attempt(schedule_state, mechanism)
                return ControllerOp(
                    Action.FEEDBACK,
                    feedback_mechanism=mechanism,
                )

        if ctx.last_action is None:
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.GENERATE:
            if _is_terminal_generate_failure(ctx.last_stop_reason):
                return ControllerOp(Action.TERMINATE)
            if tokens_left <= 0:
                if can_verify:
                    return ControllerOp(
                        Action.VERIFY,
                        verification_granularity=_select_verify_granularity(self.config, is_closed),
                    )
                return ControllerOp(Action.TERMINATE)
            if can_verify:
                return ControllerOp(
                    Action.VERIFY,
                    verification_granularity=_select_verify_granularity(self.config, is_closed),
                )
            if is_closed:
                return ControllerOp(Action.TERMINATE)
            return ControllerOp(Action.GENERATE)

        if ctx.last_action == Action.VERIFY:
            if ctx.last_render_status != RenderStatus.OK:
                self._reset_stmt_stall_state()
                if is_closed:
                    return ControllerOp(Action.TERMINATE)
                return _continue_or_terminate(tokens_left)
            if not ctx.last_outputs:
                self._reset_stmt_stall_state()
                if is_closed:
                    return ControllerOp(Action.COMMIT)
                if self.config.commit_when_no_oracle_selected:
                    return ControllerOp(Action.COMMIT)
                return _continue_or_terminate(tokens_left)
            if _any_fail(ctx.last_outputs):
                if is_closed:
                    self._reset_stmt_stall_state()
                    return ControllerOp(Action.TERMINATE)
                if self.config.enable_rollback:
                    scope = self._select_fail_scope(ctx)
                    self._pending_fail_snapshot = _FailSnapshot(
                        failed_prefix=ctx.state.prefix,
                        scope=scope,
                        error_count=_error_count(ctx.last_outputs),
                    )
                    return ControllerOp(Action.ROLLBACK, rollback_scope=scope)
                self._reset_stmt_stall_state()
                return _continue_or_terminate(tokens_left)
            self._reset_stmt_stall_state()
            if _all_pass(ctx.last_outputs):
                return ControllerOp(Action.COMMIT)
            if is_closed:
                return ControllerOp(Action.TERMINATE)
            return _continue_or_terminate(tokens_left)

        if ctx.last_action == Action.CONTINUE:
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.COMMIT:
            if is_closed:
                return ControllerOp(Action.TERMINATE)
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.ROLLBACK:
            return _generate_or_terminate(tokens_left)

        if ctx.last_action == Action.TERMINATE:
            return ControllerOp(Action.TERMINATE)

        return ControllerOp(Action.TERMINATE)

    def _apply_pending_fail_snapshot(self, schedule_state: _RepairScheduleState, ctx) -> None:
        snapshot = self._pending_fail_snapshot
        if snapshot is None or ctx.failed_prefix is None:
            return
        if snapshot.failed_prefix != ctx.failed_prefix:
            return
        schedule_state.last_fail_scope = snapshot.scope
        schedule_state.last_error_count = snapshot.error_count
        self._pending_fail_snapshot = None

    def _choose_feedback_mechanism(
        self,
        schedule_state: _RepairScheduleState,
        tokens_left: int,
    ) -> FeedbackMechanism | None:
        # Selection priority (high -> low):
        # 1) locked mechanism from prior B rounds in this key,
        # 2) explicit force mechanism in config,
        # 3) key-local default/escalation logic.
        allow_fallback = True
        if schedule_state.locked_mechanism is not None:
            preferred = schedule_state.locked_mechanism
            allow_fallback = False
        elif self.config.feedback_force_mechanism is not None:
            preferred = self.config.feedback_force_mechanism
        elif schedule_state.a_rounds == 0 and schedule_state.b_rounds == 0:
            preferred = self.config.feedback_default_mechanism
        elif _should_escalate_to_b(self.config, schedule_state):
            preferred = FeedbackMechanism.B
        else:
            preferred = FeedbackMechanism.A

        # If preferred mechanism is unavailable (round cap or token floor),
        # fallback to the other mechanism unless selection was explicitly locked.
        order = (preferred, _other_feedback_mechanism(preferred)) if allow_fallback else (preferred,)
        for mechanism in order:
            if self._mechanism_available(schedule_state, mechanism, tokens_left):
                return mechanism
        return None

    def _mechanism_available(
        self,
        schedule_state: _RepairScheduleState,
        mechanism: FeedbackMechanism,
        tokens_left: int,
    ) -> bool:
        if mechanism == FeedbackMechanism.A:
            if _round_limit_reached(
                schedule_state.a_rounds,
                self.config.feedback_max_a_rounds_per_key,
            ):
                return False
        else:
            if _round_limit_reached(
                schedule_state.b_rounds,
                self.config.feedback_max_b_rounds_per_key,
            ):
                return False
        return tokens_left >= _feedback_required_tokens(self.config, mechanism)

    def _record_mechanism_attempt(
        self,
        schedule_state: _RepairScheduleState,
        mechanism: FeedbackMechanism,
    ) -> None:
        if mechanism == FeedbackMechanism.A:
            schedule_state.a_rounds += 1
        else:
            schedule_state.b_rounds += 1
            schedule_state.locked_mechanism = FeedbackMechanism.B

    def _reset_stmt_stall_state(self) -> None:
        self._stmt_stall_key = None
        self._stmt_stall_retries = 0

    def _select_fail_scope(self, ctx) -> Granularity:
        scope = _select_fail_scope(self.config, ctx.last_outputs)
        if scope != Granularity.STMT:
            self._reset_stmt_stall_state()
            return scope

        key = _stmt_stall_key(ctx)
        if key != self._stmt_stall_key:
            self._stmt_stall_key = key
            self._stmt_stall_retries = 1
        else:
            self._stmt_stall_retries += 1

        max_stmt_retries = max(0, self.config.stmt_stall_max_retries_before_escalation)
        if self._stmt_stall_retries <= max_stmt_retries:
            return Granularity.STMT
        if _has_active_block(ctx):
            return Granularity.BLOCK
        return Granularity.FUNC

    def select_oracles(
        self,
        artifact: Artifact,
        budget: Budget,
        available: Sequence[Oracle],
        *,
        selection_granularity: Granularity | None = None,
    ) -> list[Oracle]:
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
            min_granularity=self.config.boundary_granularity,
        )


def _tokens_left(budget: Budget) -> int:
    return max(0, budget.gen_tokens_budget - budget.gen_tokens_used)


def _is_boundary_suffix(prefix: str) -> bool:
    return prefix.rstrip().endswith((";", "}"))


def _is_write_region_closed(stop_reason: StopReason | None) -> bool:
    return stop_reason is not None and stop_reason.kind == "write_region_closed"


def _can_verify(config: DefaultPolicyConfig, is_boundary: bool, is_closed: bool) -> bool:
    return (config.verify_on_boundary and is_boundary) or (config.verify_on_close and is_closed)


def _select_verify_granularity(config: DefaultPolicyConfig, is_closed: bool) -> Granularity:
    return config.close_granularity if is_closed else config.boundary_granularity


def _is_terminal_generate_failure(stop_reason: StopReason | None) -> bool:
    if stop_reason is None:
        return False
    return stop_reason.kind in {
        "no_write_region_eos",
        "unterminated_write_region",
        "invalid_write_region_payload",
    }


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
    # NOTE: Treat NOT_APPLICABLE as neutral; require at least one PASS and no FAIL.
    saw_pass = False
    for output in outputs:
        if output.verdict == Verdict.FAIL:
            return False
        if output.verdict == Verdict.PASS:
            saw_pass = True
    return saw_pass


def _select_fail_scope(config: DefaultPolicyConfig, outputs: tuple[OracleOutput, ...]) -> Granularity:
    fail_outputs = [o for o in outputs if o.verdict == Verdict.FAIL]
    scopes = [o.rollback_scope for o in fail_outputs if o.rollback_scope is not None]
    if scopes:
        return min(max(scopes), Granularity.FUNC)
    if config.enable_cdhr:
        for output in outputs:
            for diag in output.diagnostics:
                if diag.hint_scope is not None:
                    return min(diag.hint_scope, Granularity.FUNC)
    return min(config.default_fail_scope, Granularity.FUNC)


def _stmt_stall_key(ctx) -> tuple[str, tuple[Granularity, ...]]:
    anchor_prefix = ""
    if ctx.rollback.stmt_checkpoints:
        anchor_prefix = ctx.rollback.stmt_checkpoints[-1].code_prefix
    active_groups = tuple(frame.kind for frame in ctx.rollback.group_stack)
    return (anchor_prefix, active_groups)


def _has_active_block(ctx) -> bool:
    return any(frame.kind == Granularity.BLOCK for frame in ctx.rollback.group_stack)


def _repair_key(ctx) -> tuple[str, Granularity] | None:
    if ctx.repair_base_prefix is None or ctx.repair_scope is None:
        return None
    return (ctx.repair_base_prefix, ctx.repair_scope)


def _can_start_repair(
    config: DefaultPolicyConfig,
    rounds: dict[tuple[str, Granularity], int],
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


def _record_repair_round(rounds: dict[tuple[str, Granularity], int], ctx) -> None:
    key = _repair_key(ctx)
    if key is None:
        return
    rounds[key] = rounds.get(key, 0) + 1


_ERROR_LEVELS = {"error", "fatal"}


def _error_count(outputs: tuple[OracleOutput, ...]) -> int:
    return sum(
        1
        for output in outputs
        if output.verdict == Verdict.FAIL
        for diag in output.diagnostics
        if _is_error_level(diag.severity)
    )



def _should_escalate_to_b(
    config: DefaultPolicyConfig,
    schedule_state: _RepairScheduleState,
) -> bool:
    # Escalation applies after at least one A round in the same repair key.
    if schedule_state.a_rounds == 0:
        return False
    if (
        schedule_state.last_fail_scope is not None
        and schedule_state.last_fail_scope >= config.feedback_scope_escalation
    ):
        return True # FIXME: This may be too aggressive
    return schedule_state.last_error_count >= config.feedback_error_escalation_threshold


def _other_feedback_mechanism(mechanism: FeedbackMechanism) -> FeedbackMechanism:
    if mechanism == FeedbackMechanism.A:
        return FeedbackMechanism.B
    return FeedbackMechanism.A


def _feedback_required_tokens(
    config: DefaultPolicyConfig,
    mechanism: FeedbackMechanism,
) -> int:
    floor = config.feedback_min_tokens_a
    if mechanism == FeedbackMechanism.B:
        floor = config.feedback_min_tokens_b
    return config.feedback_budget_reserve_tokens + floor


def _round_limit_reached(rounds_used: int, limit: int | None) -> bool:
    if limit is None:
        return False
    return rounds_used >= limit


def _is_error_level(severity: str) -> bool:
    level = severity.lower().strip()
    return level in _ERROR_LEVELS
