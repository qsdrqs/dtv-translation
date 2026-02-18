from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from core.budget import Budget
from core.interfaces import Generator, Oracle, OracleRunner, Renderer
from core.llm_output import (
    AssistantContent,
    FenceState,
    OutputExtractorState,
    merge_assistant_content,
)
from core.logger import get_logger
from core.types import (
    Action,
    Artifact,
    ControllerState,
    FeedbackMechanism,
    FeedbackMode,
    GenerateContext,
    GenerateMessage,
    GenerationChannel,
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
from feedback.formatter import RepairFeedbackFormatConfig
from feedback.feedback import FeedbackState
from feedback.output_parser import parse_feedback_output, validate_patch_scope
from feedback.plan import FeedbackPlan, build_feedback_plan
from feedback.repair_context import RepairContext
from feedback.strategies import AssistantInlineRepair, FeedbackStrategy, UserRoundRepair
from rollback.manager import RollbackManager

logger = get_logger(__name__)

@dataclass(frozen=True)
class ControllerOp:
    action: Action
    verification_granularity: Granularity | None = None
    rollback_scope: RollbackScope | None = None
    feedback_mode: FeedbackMode | None = None
    feedback_mechanism: FeedbackMechanism | None = None


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
    last_verification_granularity: Granularity | None = None
    last_group_stack: tuple[GroupStackFrame, ...] | None = None
    last_closed_stack: tuple[GroupStackFrame, ...] = ()
    assistant_prefix: AssistantContent = field(default_factory=AssistantContent.empty)
    extractor_state: OutputExtractorState | None = None
    failed_prefix: str | None = None
    failed_assistant_prefix: AssistantContent | None = None
    failed_extractor_state: OutputExtractorState | None = None
    pending_patch: str | None = None
    repair_base_prefix: str | None = None
    repair_base_assistant_prefix: AssistantContent | None = None
    repair_base_extractor_state: OutputExtractorState | None = None
    repair_scope: RollbackScope | None = None
    feedback_parser_error: str | None = None
    last_feedback_mechanism: FeedbackMechanism | None = None


class Policy(Protocol):
    def next_action(self, ctx: PolicyContext) -> ControllerOp:
        ...

    def select_oracles(
        self,
        artifact: Artifact,
        budget: Budget,
        available: Sequence[Oracle],
        *,
        selection_granularity: Granularity | None = None,
    ) -> list[Oracle]:
        ...


def select_oracles_by_granularity(
    artifact: Artifact,
    budget: Budget,
    available: Sequence[Oracle],
    *,
    selection_granularity: Granularity,
    min_granularity: Granularity | None = None,
) -> list[Oracle]:
    _ = budget
    # Terms used in granularity filtering:
    # - required_granularity: each oracle's declared scope (e.g., STMT/FUNC/PROGRAM).
    # - boundary_granularity (min_granularity): policy lower bound; skip oracles below it.
    # - effective_boundary (selection_granularity): actual closed boundary upper bound for this verify.
    actual_granularity = selection_granularity
    selected: list[Oracle] = []
    for oracle in available:
        if actual_granularity < oracle.required_granularity:
            continue
        if min_granularity is not None and oracle.required_granularity < min_granularity:
            continue
        selected.append(oracle)
    return selected


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
            output = oracle.run(state, artifact, context)
            if output.rollback_scope is None:
                output = replace(output, rollback_scope=oracle.rollback_scope)
            outputs.append(output)
        return outputs


def update_last_assistant(messages: list[GenerateMessage], content: str | AssistantContent) -> None:
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


def _policy_feedback_enabled(policy: Policy) -> bool:
    config = getattr(policy, "config", None)
    if config is not None and hasattr(config, "enable_feedback"):
        return bool(getattr(config, "enable_feedback"))
    return True


def _feedback_strategy_for_mechanism(mechanism: FeedbackMechanism) -> FeedbackStrategy:
    if mechanism == FeedbackMechanism.B:
        return UserRoundRepair()
    # Default to A
    return AssistantInlineRepair()


def _select_feedback_generator(
    *,
    generator: Generator,
    feedback_generator: Generator | None,
    feedback_plan: FeedbackPlan,
) -> Generator:
    if feedback_plan.mode != FeedbackMode.FENCED:
        return generator
    if feedback_generator is not None:
        return feedback_generator
    return generator


def _prepare_feedback_extractor_state(
    *,
    feedback_gen: Generator,
    feedback_plan: FeedbackPlan,
    repair_base_extractor_state: OutputExtractorState,
) -> None:
    if feedback_plan.mode == FeedbackMode.FENCED:
        feedback_gen.reset_output_extractor()
        return
    if feedback_plan.channel == GenerationChannel.CONTINUATION:
        feedback_gen.restore_output_extractor_state(repair_base_extractor_state)


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"...<truncated {len(s) - max_chars} chars>"


def _failed_snippet(base_prefix: str, failed_prefix: str) -> str:
    if failed_prefix.startswith(base_prefix):
        return failed_prefix[len(base_prefix) :]
    return failed_prefix


def _clear_repair_context(runtime: ControllerRuntime) -> None:
    runtime.failed_prefix = None
    runtime.failed_assistant_prefix = None
    runtime.failed_extractor_state = None
    runtime.pending_patch = None
    runtime.repair_base_prefix = None
    runtime.repair_base_assistant_prefix = None
    runtime.repair_base_extractor_state = None
    runtime.repair_scope = None
    runtime.feedback_parser_error = None


def _fence_start_only(content: AssistantContent | None) -> AssistantContent:
    if content is None or not content.fence_lang:
        return AssistantContent.empty()
    return AssistantContent(
        pre_fence=content.pre_fence,
        fence_lang=content.fence_lang,
        code="",
        post_fence="",
        pending_text="",
        fence_state=FenceState.INSIDE,
    )


def _restore_inside_from_anchor(anchor: AssistantContent, code_prefix: str) -> AssistantContent:
    return AssistantContent(
        pre_fence=anchor.pre_fence,
        fence_lang=anchor.fence_lang,
        code=code_prefix,
        post_fence="",
        pending_text="",
        fence_state=FenceState.INSIDE,
    )


def _assert_extractor_consistency(runtime: ControllerRuntime) -> None:
    if runtime.extractor_state is None:
        return
    if runtime.extractor_state.segment.state != runtime.assistant_prefix.fence_state:
        raise RuntimeError(
            "assistant fence state diverged from segment parser state "
            f"({runtime.assistant_prefix.fence_state} vs {runtime.extractor_state.segment.state})"
        )


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


def _effective_boundary_granularity(
    op_granularity: Granularity,
    closed_stack: tuple[GroupStackFrame, ...],
) -> Granularity:
    # Use the highest closed boundary as the effective upper bound.
    if op_granularity == Granularity.PROGRAM:
        # EOS verification always uses PROGRAM as the upper bound.
        return Granularity.PROGRAM
    if any(frame.kind == Granularity.FUNC for frame in closed_stack):
        return Granularity.FUNC
    if any(frame.kind == Granularity.BLOCK for frame in closed_stack):
        return Granularity.BLOCK
    return Granularity.STMT


def _append_trace(
    trace: list[TraceEvent],
    *,
    step: int,
    stop_reason: StopReason | None,
    action: Action,
    verification_granularity: Granularity | None,
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
            verification_granularity=verification_granularity,
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
    feedback_enabled: bool,
    rollback_manager: RollbackManager,
    trace: list[TraceEvent],
) -> None:
    context.extract_fence = True
    context.channel = GenerationChannel.CONTINUATION
    feedback = feedback_state.encode()
    if (
        feedback_enabled
        and feedback
        and runtime.failed_prefix is not None
        and runtime.repair_base_prefix is not None
    ):
        raise RuntimeError("Action.GENERATE cannot include feedback payload; use Action.FEEDBACK")
    if runtime.extractor_state is None:
        runtime.extractor_state = generator.capture_output_extractor_state()
    _assert_extractor_consistency(runtime)
    generator.restore_output_extractor_state(runtime.extractor_state)
    update_last_assistant(base_messages, runtime.assistant_prefix)
    context.messages = list(base_messages)
    result = generator.generate_step(context)
    runtime.state.prefix += result.delta_text
    assistant_delta = result.assistant_delta or AssistantContent.from_unfenced(result.delta_text)
    runtime.assistant_prefix = merge_assistant_content(runtime.assistant_prefix, assistant_delta)
    runtime.extractor_state = generator.capture_output_extractor_state()
    if rollback_manager.fence_anchor is None and runtime.assistant_prefix.fence_lang:
        anchor_assistant = _fence_start_only(runtime.assistant_prefix)
        anchor_state = runtime.extractor_state.force_inside() if runtime.extractor_state else None
        rollback_manager.set_fence_anchor(anchor_assistant, anchor_state)
    budget.add_tokens(result.delta_tokens)
    runtime.last_stop_reason = result.stop_reason
    runtime.last_render_status = None
    runtime.last_artifact = None
    runtime.last_outputs = ()
    runtime.last_closed_stack = ()
    runtime.last_verification_granularity = None
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
        verification_granularity=None,
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
    feedback_enabled: bool,
    trace: list[TraceEvent],
) -> None:
    if op.verification_granularity is None:
        raise ValueError("VERIFY requires granularity")
    # Render the current prefix and update runtime state
    render_result = renderer.try_render(runtime.state.prefix)
    logger.info(
        "verify: step=%s verification_granularity=%s render_status=%s",
        runtime.state.step,
        op.verification_granularity,
        render_result.status,
    )
    runtime.last_render_status = render_result.status
    runtime.last_artifact = render_result.artifact if render_result.status == RenderStatus.OK else None
    outputs: list[OracleOutput] = []
    notes = render_result.notes
    oracle_context = OracleContext()
    effective_granularity = op.verification_granularity
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
        effective_granularity = _effective_boundary_granularity(
            op.verification_granularity,
            runtime.last_closed_stack,
        )
        # Select and run oracles, update budget and feedback
        selected_oracles = policy.select_oracles(
            runtime.last_artifact,
            budget,
            oracles,
            selection_granularity=effective_granularity,
        )
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
                if output.verdict == Verdict.FAIL and output.diagnostics:
                    max_items = 6
                    max_chars = 800
                    for diag in output.diagnostics[:max_items]:
                        logger.info(
                            "oracle_diag: oracle=%s error_code=%s message=%s",
                            output.oracle_name,
                            diag.error_code,
                            _truncate(diag.message, max_chars),
                        )
                    if len(output.diagnostics) > max_items:
                        logger.info(
                            "oracle_diag: oracle=%s message=%s",
                            output.oracle_name,
                            f"...<omitted {len(output.diagnostics) - max_items} diagnostics>",
                        )
            if feedback_enabled:
                feedback_state.update(outputs)
        else:
            notes = notes or "no oracles selected"
    else:
        runtime.last_closed_stack = ()
    runtime.last_outputs = tuple(outputs)
    runtime.last_verification_granularity = effective_granularity

    # Handle repair context based on oracle verdicts
    if feedback_enabled:
        if outputs:
            if any(out.verdict == Verdict.FAIL for out in outputs):
                runtime.failed_prefix = runtime.state.prefix
                runtime.failed_assistant_prefix = runtime.assistant_prefix
                runtime.failed_extractor_state = runtime.extractor_state
            elif all(out.verdict == Verdict.PASS for out in outputs):
                _clear_repair_context(runtime)
    else:
        _clear_repair_context(runtime)
    runtime.last_action = Action.VERIFY

    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.VERIFY,
        verification_granularity=effective_granularity,
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
    rollback_manager.add_stmt_checkpoint(
        runtime.state.prefix,
        runtime.assistant_prefix,
        runtime.extractor_state,
    )
    _clear_repair_context(runtime)
    runtime.last_action = Action.COMMIT
    logger.info(
        "commit: step=%s verification_granularity=%s prefix_len=%s",
        runtime.state.step,
        runtime.last_verification_granularity,
        len(runtime.state.prefix),
    )
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.COMMIT,
        verification_granularity=runtime.last_verification_granularity,
        budget=budget,
        oracle_outputs=runtime.last_outputs,
    )


def _handle_rollback(
    runtime: ControllerRuntime,
    op: ControllerOp,
    generator: Generator,
    rollback_manager: RollbackManager,
    feedback_state: FeedbackState,
    feedback_enabled: bool,
    budget: Budget,
    trace: list[TraceEvent],
) -> None:
    if op.rollback_scope is None:
        raise ValueError("ROLLBACK requires rollback_scope")
    snapshot = rollback_manager.rollback(op.rollback_scope)
    runtime.state.prefix = snapshot.code_prefix
    runtime.assistant_prefix = snapshot.assistant_prefix
    runtime.extractor_state = snapshot.extractor_state
    if rollback_manager.fence_anchor is not None:
        runtime.assistant_prefix = _restore_inside_from_anchor(
            rollback_manager.fence_anchor.assistant_prefix,
            runtime.state.prefix,
        )
        if runtime.extractor_state is None:
            runtime.extractor_state = rollback_manager.fence_anchor.extractor_state
        if runtime.extractor_state is None:
            runtime.extractor_state = generator.capture_output_extractor_state()
        runtime.extractor_state = runtime.extractor_state.force_inside()
    elif runtime.extractor_state is None:
        runtime.extractor_state = generator.capture_output_extractor_state()
    generator.restore_output_extractor_state(runtime.extractor_state)
    if feedback_enabled:
        feedback_state.update(list(runtime.last_outputs), selected_scope=op.rollback_scope)
        runtime.pending_patch = None
        runtime.repair_base_prefix = runtime.state.prefix
        runtime.repair_base_assistant_prefix = runtime.assistant_prefix
        runtime.repair_base_extractor_state = runtime.extractor_state
        runtime.repair_scope = op.rollback_scope
    else:
        _clear_repair_context(runtime)
    runtime.last_render_status = None
    runtime.last_artifact = None
    runtime.last_outputs = ()
    runtime.last_group_stack = None
    runtime.last_closed_stack = ()
    runtime.last_verification_granularity = None
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
        verification_granularity=None,
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
    repair_feedback_format_config: RepairFeedbackFormatConfig | None,
    trace: list[TraceEvent],
) -> None:
    if (
        runtime.failed_prefix is None
        or runtime.repair_base_prefix is None
        or runtime.repair_base_assistant_prefix is None
        or runtime.repair_base_extractor_state is None
    ):
        raise RuntimeError("FEEDBACK requires failed_prefix and repair base prefix.")
    mechanism = op.feedback_mechanism or FeedbackMechanism.A
    bad_snippet = _failed_snippet(runtime.repair_base_prefix, runtime.failed_prefix)
    repair_context = RepairContext.from_feedback_state(
        feedback_state,
        bad_snippet,
        repair_scope=runtime.repair_scope or RollbackScope.STMT,
        parser_error_context=runtime.feedback_parser_error,
    )
    feedback_plan = build_feedback_plan(
        mechanism=mechanism,
        requested_mode=op.feedback_mode,
        repair_context=repair_context,
        repair_feedback_format_config=repair_feedback_format_config,
    )
    feedback_strategy = _feedback_strategy_for_mechanism(feedback_plan.mechanism)
    feedback_gen = _select_feedback_generator(
        generator=generator,
        feedback_generator=feedback_generator,
        feedback_plan=feedback_plan,
    )
    _prepare_feedback_extractor_state(
        feedback_gen=feedback_gen,
        feedback_plan=feedback_plan,
        repair_base_extractor_state=runtime.repair_base_extractor_state,
    )
    context.extract_fence = feedback_plan.channel == GenerationChannel.CONTINUATION
    context.channel = feedback_plan.channel
    update_last_assistant(base_messages, runtime.repair_base_assistant_prefix)
    context.messages = feedback_strategy.apply(
        base_messages,
        feedback_plan.prompt,
        runtime.repair_base_assistant_prefix,
    )
    result = feedback_gen.generate_step(context)
    if feedback_gen is generator:
        generator.restore_output_extractor_state(runtime.repair_base_extractor_state)
    if feedback_plan.channel == GenerationChannel.PATCH:
        parse_result = parse_feedback_output(result.delta_text)
        scope = runtime.repair_scope or RollbackScope.STMT
        scope_error = None
        if parse_result.patch is not None:
            scope_error = validate_patch_scope(parse_result.patch, scope)
        runtime.pending_patch = parse_result.patch
        runtime.feedback_parser_error = parse_result.error or scope_error
        if runtime.feedback_parser_error is not None:
            runtime.pending_patch = None
    else:
        runtime.pending_patch = result.delta_text
        runtime.feedback_parser_error = None
    runtime.last_feedback_mechanism = feedback_plan.mechanism
    budget.add_tokens(result.delta_tokens)
    runtime.last_stop_reason = result.stop_reason
    runtime.last_action = Action.FEEDBACK
    patch_len = len(runtime.pending_patch) if runtime.pending_patch is not None else 0
    logger.info(
        "feedback: step=%s mechanism=%s delta_tokens=%s stop_reason=%s patch_len=%s parse_error=%s",
        runtime.state.step,
        feedback_plan.mechanism,
        result.delta_tokens,
        result.stop_reason.kind,
        patch_len,
        runtime.feedback_parser_error,
    )
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.FEEDBACK,
        verification_granularity=None,
        budget=budget,
        notes=f"feedback_mechanism={feedback_plan.mechanism.value}",
    )


def _handle_apply_patch(
    runtime: ControllerRuntime,
    budget: Budget,
    trace: list[TraceEvent],
) -> None:
    if (
        runtime.pending_patch is None
        or runtime.repair_base_prefix is None
        or runtime.repair_base_assistant_prefix is None
        or runtime.repair_base_extractor_state is None
    ):
        raise RuntimeError("APPLY_PATCH requires pending_patch and repair base prefix.")
    patch_len = len(runtime.pending_patch)
    runtime.state.prefix = f"{runtime.repair_base_prefix}{runtime.pending_patch}"
    runtime.assistant_prefix = runtime.repair_base_assistant_prefix.with_code(runtime.state.prefix)
    runtime.extractor_state = runtime.repair_base_extractor_state
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
        patch_len,
        len(runtime.state.prefix),
    )
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.APPLY_PATCH,
        verification_granularity=None,
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
        verification_granularity=None,
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
        verification_granularity=None,
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
    repair_feedback_format_config: RepairFeedbackFormatConfig | None = None,
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
    if oracle_runner is None:
        oracle_runner = DummyOracleRunner()
    oracle_runner_impl: OracleRunner = oracle_runner
    feedback_enabled = _policy_feedback_enabled(policy)

    runtime = ControllerRuntime(state=ControllerState(prefix=""))
    runtime.extractor_state = generator.capture_output_extractor_state()
    trace: list[TraceEvent] = []

    base_messages: list[GenerateMessage] = []
    if prompt_prefix:
        base_messages.append(GenerateMessage(role="user", content=prompt_prefix, stop=True))
    base_messages.append(
        GenerateMessage(role="assistant", content=AssistantContent.empty(), stop=False)
    )
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
            "policy: step=%s action=%s verification_granularity=%s rollback_scope=%s feedback_mode=%s feedback_mechanism=%s tokens_used=%s tokens_left=%s",
            runtime.state.step,
            op.action,
            op.verification_granularity,
            op.rollback_scope,
            op.feedback_mode,
            op.feedback_mechanism,
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
                feedback_enabled,
                rollback_manager,
                trace,
            )
            runtime.state.step += 1
            # Terminate immediately if the model ended without producing a rust fence.
            if runtime.last_stop_reason is not None and runtime.last_stop_reason.kind in {
                "no_fence_eos",
            }:
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
                feedback_enabled,
                trace,
            )
            runtime.state.step += 1
            continue

        if op.action == Action.COMMIT:
            _handle_commit(runtime, rollback_manager, budget, trace)
            runtime.state.step += 1
            continue

        if op.action == Action.ROLLBACK:
            _handle_rollback(
                runtime,
                op,
                generator,
                rollback_manager,
                feedback_state,
                feedback_enabled,
                budget,
                trace,
            )
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
                repair_feedback_format_config,
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
