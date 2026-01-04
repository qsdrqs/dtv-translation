from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from core.budget import Budget
from core.interfaces import Generator, Oracle, OracleRunner, Renderer
from core.logger import get_logger
from core.types import (
    Action,
    Artifact,
    ControllerState,
    GenerateContext,
    GenerateMessage,
    Granularity,
    OracleOutput,
    RenderStatus,
    RollbackScope,
    StopReason,
    TraceEvent,
    Verdict,
)
from feedback.strategies import AppendToLastAssistant, FeedbackStrategy
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager

logger = get_logger(__name__)


_GRANULARITY_ORDER = {
    Granularity.STMT: 0,
    Granularity.BLOCK: 1,
    Granularity.FUNC: 2,
    Granularity.PROGRAM: 3,
}


def _granularity_at_least(actual: Granularity, required: Granularity) -> bool:
    return _GRANULARITY_ORDER[actual] >= _GRANULARITY_ORDER[required]


@dataclass(frozen=True)
class ControllerOp:
    action: Action
    granularity: Granularity | None = None
    rollback_scope: RollbackScope | None = None


@dataclass(frozen=True)
class PolicyContext:
    state: ControllerState
    budget: Budget
    rollback: RollbackManager
    last_action: Action | None
    last_stop_reason: StopReason | None
    last_render_status: RenderStatus | None
    last_artifact: Artifact | None
    last_outputs: tuple[OracleOutput, ...]
    failed_prefix: str | None
    pending_patch: str | None
    repair_base_prefix: str | None


@dataclass
class ControllerRuntime:
    state: ControllerState
    last_action: Action | None = None
    last_stop_reason: StopReason | None = None
    last_render_status: RenderStatus | None = None
    last_artifact: Artifact | None = None
    last_outputs: tuple[OracleOutput, ...] = ()
    failed_prefix: str | None = None
    pending_patch: str | None = None
    repair_base_prefix: str | None = None


class Policy(Protocol):
    def next_action(self, ctx: PolicyContext) -> ControllerOp:
        ...

    def select_oracles(
        self,
        artifact: Artifact,
        budget: Budget,
        available: Sequence[Oracle],
    ) -> list[Oracle]:
        ...


def select_oracles_by_granularity(
    artifact: Artifact,
    budget: Budget,
    available: Sequence[Oracle],
) -> list[Oracle]:
    _ = budget
    return [
        oracle
        for oracle in available
        if _granularity_at_least(artifact.granularity, oracle.required_granularity)
    ]


class DummyOracleRunner:
    def run(self, oracles: list[Oracle], state: ControllerState, artifact: Artifact) -> list[OracleOutput]:
        outputs: list[OracleOutput] = []
        for oracle in oracles:
            outputs.append(oracle.run(state, artifact))
        return outputs


def update_last_assistant(messages: list[GenerateMessage], content: str) -> None:
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].role == "assistant":
            messages[idx] = GenerateMessage(
                role="assistant",
                content=content,
                stop=messages[idx].stop,
            )
            return
    messages.append(GenerateMessage(role="assistant", content=content))


def _remaining_tokens(budget: Budget) -> int:
    return max(0, budget.gen_tokens_budget - budget.gen_tokens_used)


def _build_repair_feedback(feedback_state: FeedbackState, bad_snippet: str) -> str:
    diagnostics = feedback_state.encode().strip()
    if not diagnostics:
        diagnostics = "(no diagnostics)"
    if not bad_snippet:
        bad_snippet = "(empty)"
    return "\n".join(
        [
            "# Repair Request",
            "Replace the failed snippet with a corrected version.",
            "Output only the replacement code.",
            "",
            "## Diagnostics",
            diagnostics,
            "",
            "## Failed Snippet",
            bad_snippet,
        ]
    )


def _failed_snippet(base_prefix: str, failed_prefix: str) -> str:
    if failed_prefix.startswith(base_prefix):
        return failed_prefix[len(base_prefix) :]
    return failed_prefix


def _clear_repair_context(runtime: ControllerRuntime) -> None:
    runtime.failed_prefix = None
    runtime.pending_patch = None
    runtime.repair_base_prefix = None


def _append_trace(
    trace: list[TraceEvent],
    *,
    step: int,
    stop_reason: StopReason | None,
    action: Action,
    granularity: Granularity | None,
    budget: Budget,
    oracle_outputs: tuple[OracleOutput, ...] = (),
    render_status: RenderStatus | None = None,
    rollback_scope: RollbackScope | None = None,
    patch_applied: bool = False,
    notes: str = "",
) -> None:
    trace.append(
        TraceEvent(
            step=step,
            stop_reason=stop_reason,
            action=action,
            granularity=granularity,
            render_status=render_status,
            rollback_scope=rollback_scope,
            patch_applied=patch_applied,
            budget_snapshot=budget.snapshot(),
            oracle_outputs=oracle_outputs,
            notes=notes,
        )
    )


def _handle_generate(
    runtime: ControllerRuntime,
    base_messages: list[GenerateMessage],
    context: GenerateContext,
    generator: Generator,
    budget: Budget,
    feedback_state: FeedbackState,
    feedback_strategy: FeedbackStrategy,
    trace: list[TraceEvent],
) -> None:
    update_last_assistant(base_messages, runtime.state.prefix)
    feedback = feedback_state.encode()
    context.messages = feedback_strategy.apply(base_messages, feedback, runtime.state.prefix)
    result = generator.generate_step(context)
    runtime.state.prefix += result.delta_text
    budget.add_tokens(result.delta_tokens)
    runtime.last_stop_reason = result.stop_reason
    runtime.last_render_status = None
    runtime.last_artifact = None
    runtime.last_outputs = ()
    runtime.last_action = Action.GENERATE
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.GENERATE,
        granularity=None,
        budget=budget,
    )


def _handle_verify(
    runtime: ControllerRuntime,
    op: ControllerOp,
    renderer: Renderer,
    policy: Policy,
    oracles: Sequence[Oracle],
    oracle_runner: OracleRunner,
    budget: Budget,
    feedback_state: FeedbackState,
    trace: list[TraceEvent],
) -> None:
    if op.granularity is None:
        raise ValueError("VERIFY requires granularity")
    render_result = renderer.try_render(runtime.state.prefix, op.granularity)
    runtime.last_render_status = render_result.status
    runtime.last_artifact = render_result.artifact if render_result.status == RenderStatus.OK else None
    outputs: list[OracleOutput] = []
    notes = render_result.notes
    if render_result.status == RenderStatus.OK and runtime.last_artifact is not None:
        selected_oracles = policy.select_oracles(runtime.last_artifact, budget, oracles)
        if selected_oracles:
            outputs = oracle_runner.run(selected_oracles, runtime.state, runtime.last_artifact)
            for output in outputs:
                budget.record_oracle_call(output.oracle_name, output.realized_cost)
            feedback_state.update(outputs)
        else:
            notes = notes or "no oracles selected"
    runtime.last_outputs = tuple(outputs)

    if outputs:
        if any(out.verdict == Verdict.FAIL for out in outputs):
            runtime.failed_prefix = runtime.state.prefix
        elif all(out.verdict == Verdict.PASS for out in outputs):
            _clear_repair_context(runtime)
    runtime.last_action = Action.VERIFY

    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.VERIFY,
        granularity=op.granularity,
        budget=budget,
        oracle_outputs=runtime.last_outputs,
        render_status=runtime.last_render_status,
        notes=notes or "",
    )


def _handle_commit(
    runtime: ControllerRuntime,
    rollback_manager: RollbackManager,
    budget: Budget,
    trace: list[TraceEvent],
) -> None:
    if runtime.last_artifact is None:
        raise RuntimeError("COMMIT requires a verified artifact.")
    rollback_manager.apply_group_events(runtime.last_artifact.group_events)
    rollback_manager.add_stmt_checkpoint(runtime.state.prefix)
    _clear_repair_context(runtime)
    runtime.last_action = Action.COMMIT
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.COMMIT,
        granularity=runtime.last_artifact.granularity,
        budget=budget,
        oracle_outputs=runtime.last_outputs,
    )


def _handle_rollback(
    runtime: ControllerRuntime,
    op: ControllerOp,
    rollback_manager: RollbackManager,
    budget: Budget,
    trace: list[TraceEvent],
) -> None:
    if op.rollback_scope is None:
        raise ValueError("ROLLBACK requires rollback_scope")
    runtime.state.prefix = rollback_manager.rollback(op.rollback_scope)
    runtime.pending_patch = None
    runtime.repair_base_prefix = runtime.state.prefix
    runtime.last_render_status = None
    runtime.last_artifact = None
    runtime.last_outputs = ()
    runtime.last_action = Action.ROLLBACK
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.ROLLBACK,
        granularity=None,
        budget=budget,
        rollback_scope=op.rollback_scope,
    )


def _handle_feedback(
    runtime: ControllerRuntime,
    base_messages: list[GenerateMessage],
    context: GenerateContext,
    generator: Generator,
    budget: Budget,
    feedback_state: FeedbackState,
    feedback_strategy: FeedbackStrategy,
    trace: list[TraceEvent],
) -> None:
    if runtime.failed_prefix is None or runtime.repair_base_prefix is None:
        raise RuntimeError("FEEDBACK requires failed_prefix and repair base prefix.")
    bad_snippet = _failed_snippet(runtime.repair_base_prefix, runtime.failed_prefix)
    repair_feedback = _build_repair_feedback(feedback_state, bad_snippet)
    update_last_assistant(base_messages, runtime.repair_base_prefix)
    context.messages = feedback_strategy.apply(base_messages, repair_feedback, runtime.repair_base_prefix)
    result = generator.generate_step(context)
    runtime.pending_patch = result.delta_text
    budget.add_tokens(result.delta_tokens)
    runtime.last_stop_reason = result.stop_reason
    runtime.last_action = Action.FEEDBACK
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.FEEDBACK,
        granularity=None,
        budget=budget,
    )


def _handle_apply_patch(
    runtime: ControllerRuntime,
    budget: Budget,
    trace: list[TraceEvent],
) -> None:
    if runtime.pending_patch is None or runtime.repair_base_prefix is None:
        raise RuntimeError("APPLY_PATCH requires pending_patch and repair base prefix.")
    runtime.state.prefix = f"{runtime.repair_base_prefix}{runtime.pending_patch}"
    _clear_repair_context(runtime)
    runtime.last_render_status = None
    runtime.last_artifact = None
    runtime.last_outputs = ()
    runtime.last_action = Action.APPLY_PATCH
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.APPLY_PATCH,
        granularity=None,
        budget=budget,
        patch_applied=True,
    )


def _handle_continue(
    runtime: ControllerRuntime,
    budget: Budget,
    trace: list[TraceEvent],
) -> None:
    runtime.last_action = Action.CONTINUE
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.CONTINUE,
        granularity=None,
        budget=budget,
    )


def _handle_terminate(
    runtime: ControllerRuntime,
    budget: Budget,
    trace: list[TraceEvent],
) -> None:
    runtime.last_action = Action.TERMINATE
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.TERMINATE,
        granularity=None,
        budget=budget,
    )


def run_dtv_loop(
    generator: Generator,
    renderer: Renderer,
    oracles: Sequence[Oracle],
    budget: Budget,
    feedback_state: FeedbackState,
    rollback_manager: RollbackManager,
    policy: Policy,
    feedback_strategy: FeedbackStrategy | None = None,
    max_steps: int = 100,
    max_new_length: int = 1024,
    prompt_prefix: str = "",
    oracle_runner: OracleRunner | None = None,
) -> tuple[str, list[TraceEvent]]:
    """
    State machine (MVP):
    - State vars: prefix, last_stop_reason, last_render_status, last_artifact, last_outputs,
      failed_prefix, repair_base_prefix, pending_patch.
    - Actions: GENERATE, VERIFY(granularity), COMMIT, ROLLBACK(scope), FEEDBACK, APPLY_PATCH,
      CONTINUE, TERMINATE.
    - VERIFY performs render + oracle runs; render CONTINUE/FAIL yields no oracle outputs.
    - FEEDBACK requires a prior failed_prefix and a repair base from ROLLBACK.
    """
    if feedback_strategy is None:
        feedback_strategy = AppendToLastAssistant()
    if oracle_runner is None:
        oracle_runner = DummyOracleRunner()

    runtime = ControllerRuntime(state=ControllerState(prefix=""))
    trace: list[TraceEvent] = []

    base_messages: list[GenerateMessage] = []
    if prompt_prefix:
        base_messages.append(GenerateMessage(role="user", content=prompt_prefix, stop=True))
    base_messages.append(GenerateMessage(role="assistant", content=""))
    context = GenerateContext(messages=base_messages, steps=0, max_new_length=max_new_length)

    while runtime.state.step < max_steps:
        ctx = PolicyContext(
            state=runtime.state,
            budget=budget,
            rollback=rollback_manager,
            last_action=runtime.last_action,
            last_stop_reason=runtime.last_stop_reason,
            last_render_status=runtime.last_render_status,
            last_artifact=runtime.last_artifact,
            last_outputs=runtime.last_outputs,
            failed_prefix=runtime.failed_prefix,
            pending_patch=runtime.pending_patch,
            repair_base_prefix=runtime.repair_base_prefix,
        )
        op = policy.next_action(ctx)

        if op.action in {Action.GENERATE, Action.FEEDBACK}:
            if _remaining_tokens(budget) <= 0:
                raise RuntimeError("Token budget exhausted but policy requested generation.")
            context.steps = runtime.state.step
            context.max_new_length = min(max_new_length, _remaining_tokens(budget))

        if op.action == Action.GENERATE:
            _handle_generate(
                runtime,
                base_messages,
                context,
                generator,
                budget,
                feedback_state,
                feedback_strategy,
                trace,
            )
            runtime.state.step += 1
            continue

        if op.action == Action.VERIFY:
            _handle_verify(
                runtime,
                op,
                renderer,
                policy,
                oracles,
                oracle_runner,
                budget,
                feedback_state,
                trace,
            )
            runtime.state.step += 1
            continue

        if op.action == Action.COMMIT:
            _handle_commit(runtime, rollback_manager, budget, trace)
            runtime.state.step += 1
            continue

        if op.action == Action.ROLLBACK:
            _handle_rollback(runtime, op, rollback_manager, budget, trace)
            runtime.state.step += 1
            continue

        if op.action == Action.FEEDBACK:
            _handle_feedback(
                runtime,
                base_messages,
                context,
                generator,
                budget,
                feedback_state,
                feedback_strategy,
                trace,
            )
            runtime.state.step += 1
            continue

        if op.action == Action.APPLY_PATCH:
            _handle_apply_patch(runtime, budget, trace)
            runtime.state.step += 1
            continue

        if op.action == Action.CONTINUE:
            _handle_continue(runtime, budget, trace)
            runtime.state.step += 1
            continue

        if op.action == Action.TERMINATE:
            _handle_terminate(runtime, budget, trace)
            break

        raise ValueError(f"Unsupported action: {op.action}")

    return runtime.state.prefix, trace
