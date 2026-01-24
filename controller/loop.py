from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from core.budget import Budget
from core.interfaces import Generator, Oracle, OracleRunner, Renderer
from core.llm_output import FenceState
from core.logger import get_logger
from core.types import (
    Action,
    Artifact,
    ControllerState,
    FeedbackMode,
    GenerateContext,
    GenerateMessage,
    Granularity,
    GroupStackFrame,
    OracleContext,
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
    feedback_mode: FeedbackMode | None = None


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
    last_group_stack: tuple[GroupStackFrame, ...] | None = None
    last_closed_stack: tuple[GroupStackFrame, ...] = ()
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
    def run(
        self,
        oracles: list[Oracle],
        state: ControllerState,
        artifact: Artifact,
        context: OracleContext,
    ) -> list[OracleOutput]:
        outputs: list[OracleOutput] = []
        for oracle in oracles:
            outputs.append(oracle.run(state, artifact, context))
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
    messages.append(GenerateMessage(role="assistant", content=content, stop=False))


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


def _closed_stack_diff(
    previous: tuple[GroupStackFrame, ...] | None,
    current: tuple[GroupStackFrame, ...] | None,
) -> tuple[GroupStackFrame, ...]:
    if not previous:
        return ()
    if current is None:
        return previous
    k = 0
    while k < len(previous) and k < len(current) and previous[k] == current[k]:
        k += 1
    return previous[k:]


def _closed_function_name(closed_stack: tuple[GroupStackFrame, ...]) -> str | None:
    if not closed_stack:
        return None
    function_frame = next(
        (frame for frame in reversed(closed_stack) if frame.kind == Granularity.FUNC and frame.name_id),
        None,
    )
    if function_frame is None:
        return None
    return function_frame.name_id


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
    # Main generation expects fenced Rust output; extract only fenced code.
    context.extract_fence = True
    if runtime.last_action == Action.ROLLBACK and not runtime.state.prefix:
        # Rollback to empty prefix implies we must restart fence tracking from scratch.
        reset_extractor = getattr(generator, "reset_output_extractor", None)
        if callable(reset_extractor):
            reset_extractor()
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
    runtime.last_closed_stack = ()
    runtime.last_action = Action.GENERATE
    logger.info(
        "generate: step=%s delta_tokens=%s stop_reason=%s prefix_len=%s",
        runtime.state.step,
        result.delta_tokens,
        result.stop_reason.kind,
        len(runtime.state.prefix),
    )
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
    # Render the current prefix and update runtime state
    render_result = renderer.try_render(runtime.state.prefix, op.granularity)
    logger.info(
        "verify: step=%s granularity=%s render_status=%s",
        runtime.state.step,
        op.granularity,
        render_result.status,
    )
    runtime.last_render_status = render_result.status
    runtime.last_artifact = render_result.artifact if render_result.status == RenderStatus.OK else None
    outputs: list[OracleOutput] = []
    notes = render_result.notes
    oracle_context = OracleContext()
    if render_result.status == RenderStatus.OK and runtime.last_artifact is not None:
        # Track group stack changes and update closed stack
        if runtime.last_artifact.group_stack is not None:
            runtime.last_closed_stack = _closed_stack_diff(
                runtime.last_group_stack,
                runtime.last_artifact.group_stack,
            )
            runtime.last_group_stack = runtime.last_artifact.group_stack
            oracle_context = OracleContext(
                closed_stack=runtime.last_closed_stack,
                closed_function_name=_closed_function_name(runtime.last_closed_stack),
            )
        else:
            runtime.last_closed_stack = ()
            runtime.last_group_stack = None
        # Select and run oracles, update budget and feedback
        selected_oracles = policy.select_oracles(runtime.last_artifact, budget, oracles)
        logger.info("verify: selected_oracles=%s", [oracle.name for oracle in selected_oracles])
        if selected_oracles:
            outputs = oracle_runner.run(
                selected_oracles,
                runtime.state,
                runtime.last_artifact,
                oracle_context,
            )
            for output in outputs:
                budget.record_oracle_call(output.oracle_name, output.realized_cost)
                logger.info(
                    "oracle_result: oracle=%s verdict=%s diagnostics=%s",
                    output.oracle_name,
                    output.verdict,
                    len(output.diagnostics),
                )
            feedback_state.update(outputs)
        else:
            notes = notes or "no oracles selected"
    else:
        runtime.last_closed_stack = ()
    runtime.last_outputs = tuple(outputs)

    # Handle repair context based on oracle verdicts
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
    if runtime.last_artifact.group_stack is not None:
        rollback_manager.sync_groups(runtime.last_artifact.group_stack)
    else:
        rollback_manager.apply_group_events(runtime.last_artifact.group_events)
    rollback_manager.add_stmt_checkpoint(runtime.state.prefix)
    _clear_repair_context(runtime)
    runtime.last_action = Action.COMMIT
    logger.info(
        "commit: step=%s granularity=%s prefix_len=%s",
        runtime.state.step,
        runtime.last_artifact.granularity,
        len(runtime.state.prefix),
    )
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
    runtime.last_group_stack = None
    runtime.last_closed_stack = ()
    runtime.last_action = Action.ROLLBACK
    logger.info(
        "rollback: step=%s scope=%s prefix_len=%s",
        runtime.state.step,
        op.rollback_scope,
        len(runtime.state.prefix),
    )
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
    op: ControllerOp,
    base_messages: list[GenerateMessage],
    context: GenerateContext,
    generator: Generator,
    feedback_generator: Generator | None,
    budget: Budget,
    feedback_state: FeedbackState,
    feedback_strategy: FeedbackStrategy,
    trace: list[TraceEvent],
) -> None:
    if runtime.failed_prefix is None or runtime.repair_base_prefix is None:
        raise RuntimeError("FEEDBACK requires failed_prefix and repair base prefix.")
    feedback_gen = generator
    if op.feedback_mode == FeedbackMode.FENCED:
        # Fenced feedback uses a dedicated generator to avoid polluting the main stream.
        if feedback_generator is None:
            raise RuntimeError("feedback_generator is required for fenced feedback mode")
        feedback_gen = feedback_generator
        reset_extractor = getattr(feedback_gen, "reset_output_extractor", None)
        if callable(reset_extractor):
            reset_extractor()
    # Feedback output is also fenced; keep extraction on for both modes.
    context.extract_fence = True
    bad_snippet = _failed_snippet(runtime.repair_base_prefix, runtime.failed_prefix)
    repair_feedback = _build_repair_feedback(feedback_state, bad_snippet)
    update_last_assistant(base_messages, runtime.repair_base_prefix)
    context.messages = feedback_strategy.apply(base_messages, repair_feedback, runtime.repair_base_prefix)
    result = feedback_gen.generate_step(context)
    runtime.pending_patch = result.delta_text
    budget.add_tokens(result.delta_tokens)
    runtime.last_stop_reason = result.stop_reason
    runtime.last_action = Action.FEEDBACK
    logger.info(
        "feedback: step=%s delta_tokens=%s stop_reason=%s patch_len=%s",
        runtime.state.step,
        result.delta_tokens,
        result.stop_reason.kind,
        len(runtime.pending_patch),
    )
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
    runtime.last_group_stack = None
    runtime.last_closed_stack = ()
    runtime.last_action = Action.APPLY_PATCH
    logger.info(
        "apply_patch: step=%s patch_len=%s prefix_len=%s",
        runtime.state.step,
        len(runtime.pending_patch),
        len(runtime.state.prefix),
    )
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
    logger.info("continue: step=%s", runtime.state.step)
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
    logger.info("terminate: step=%s", runtime.state.step)
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
    feedback_generator: Generator | None = None,
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
    oracle_runner_impl: OracleRunner = oracle_runner

    runtime = ControllerRuntime(state=ControllerState(prefix=""))
    trace: list[TraceEvent] = []

    base_messages: list[GenerateMessage] = []
    if prompt_prefix:
        base_messages.append(GenerateMessage(role="user", content=prompt_prefix, stop=True))
    base_messages.append(GenerateMessage(role="assistant", content="", stop=False))
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
        logger.info(
            "policy: step=%s action=%s granularity=%s rollback_scope=%s feedback_mode=%s tokens_used=%s tokens_left=%s",
            runtime.state.step,
            op.action,
            op.granularity,
            op.rollback_scope,
            op.feedback_mode,
            budget.gen_tokens_used,
            _remaining_tokens(budget),
        )

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
            # Terminate immediately if the model ended without producing a rust fence.
            if runtime.last_stop_reason is not None and runtime.last_stop_reason.kind == "no_fence_eos":
                _handle_terminate(runtime, budget, trace)
                break
            continue

        if op.action == Action.VERIFY:
            _handle_verify(
                runtime,
                op,
                renderer,
                policy,
                oracles,
                oracle_runner_impl,
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
            state_getter = getattr(generator, "get_output_extractor_state", None)
            if callable(state_getter):
                extractor_state = state_getter()
                # Invariant: rollback never happens after the fenced block is closed.
                assert extractor_state != FenceState.DONE, "rollback after fence closed is unsupported"
            _handle_rollback(runtime, op, rollback_manager, budget, trace)
            runtime.state.step += 1
            continue

        if op.action == Action.FEEDBACK:
            _handle_feedback(
                runtime,
                op,
                base_messages,
                context,
                generator,
                feedback_generator,
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
