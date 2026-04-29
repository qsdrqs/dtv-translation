from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from core.budget import Budget
from core.interfaces import Generator, Oracle, OracleRunner, Renderer
from core.llm_output import (
    AssistantContent,
    DEFAULT_WRITE_REGION_MARKERS,
    OutputExtractorState,
    WriteRegionMarkers,
    WriteRegionState,
    merge_assistant_content,
)
from core.logger import get_logger
from core.types import (
    Action,
    Artifact,
    ControllerState,
    FeedbackMechanism,
    GenerateContext,
    GenerateMessage,
    GenerateResult,
    GenerationChannel,
    Granularity,
    GroupStackFrame,
    OracleContext,
    OracleOutput,
    RenderStatus,
    StopReason,
    TraceEvent,
    Verdict,
)
from feedback.annotation import annotate_snippet
from feedback.formatter import RepairFeedbackFormatConfig, render_repair_feedback
from feedback.feedback import FeedbackState
from feedback.language import FeedbackLanguageConfig
from feedback.output_parser import parse_diff_feedback_output, parse_feedback_output, validate_patch_scope
from feedback.plan import FeedbackPlan, build_feedback_plan
from feedback.repair_context import RepairContext
from feedback.strategies import AssistantInlineRepair, FeedbackStrategy, UserRoundRepair
from rollback.manager import RollbackManager

logger = get_logger(__name__)

@dataclass(frozen=True)
class ControllerOp:
    action: Action
    verification_granularity: Granularity | None = None
    rollback_scope: Granularity | None = None
    feedback_mechanism: FeedbackMechanism | None = None
    bailout: bool = False


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
    repair_scope: Granularity | None
    write_region_state: WriteRegionState


@dataclass(frozen=True)
class RepairRegion:
    scope: Granularity
    base_prefix: str
    base_assistant_prefix: AssistantContent
    base_extractor_state: OutputExtractorState | None


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
    repair_regions: list[RepairRegion] = field(default_factory=list)
    feedback_parser_error: str | None = None
    last_feedback_mechanism: FeedbackMechanism | None = None

    @property
    def current_region(self) -> RepairRegion | None:
        return self.repair_regions[-1] if self.repair_regions else None

    @property
    def repair_scope(self) -> Granularity | None:
        region = self.current_region
        return region.scope if region else None

    @property
    def repair_base_prefix(self) -> str | None:
        region = self.current_region
        return region.base_prefix if region else None

    @property
    def repair_base_assistant_prefix(self) -> AssistantContent | None:
        region = self.current_region
        return region.base_assistant_prefix if region else None

    @property
    def repair_base_extractor_state(self) -> OutputExtractorState | None:
        region = self.current_region
        return region.base_extractor_state if region else None


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

    def reset_round_state(self) -> None:
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
        if oracle.required_granularity > actual_granularity:
            logger.info(
                "oracle skipped: name=%s reason=boundary_too_shallow actual=%s required=%s",
                oracle.name,
                actual_granularity,
                oracle.required_granularity,
            )
            continue
        if min_granularity is not None and oracle.required_granularity < min_granularity:
            logger.info(
                "oracle skipped: name=%s reason=below_policy_min required=%s min=%s",
                oracle.name,
                oracle.required_granularity,
                min_granularity,
            )
            continue
        selected.append(oracle)
        logger.info(
            "oracle selected: name=%s actual=%s required=%s min=%s",
            oracle.name,
            actual_granularity,
            oracle.required_granularity,
            min_granularity,
        )
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


def render_write_region_contract(
    language_name: str,
    markers: WriteRegionMarkers,
) -> str:
    return f"""When you are ready to write the final {language_name} candidate, emit exactly one write region.
You may think before {markers.begin_marker}, but inside the write region output raw code only without unnecessary comments or explanations
DO NOT use markdown fences inside the write region.

format:
{markers.begin_marker}
// Write your code here.
{markers.end_marker}

"""


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
) -> Generator:
    if feedback_generator is not None:
        return feedback_generator
    return generator


def _prepare_feedback_extractor_state(
    *,
    feedback_gen: Generator,
    feedback_plan: FeedbackPlan,
    repair_base_extractor_state: OutputExtractorState,
) -> None:
    if feedback_plan.mechanism == FeedbackMechanism.B:
        feedback_gen.reset_output_extractor()
        return
    if feedback_plan.channel == GenerationChannel.CONTINUATION:
        feedback_gen.restore_output_extractor_state(repair_base_extractor_state)


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"...<truncated {len(s) - max_chars} chars>"


def _snippet_start_line(base_prefix: str) -> int:
    return base_prefix.count("\n") + 1


def _failed_snippet(base_prefix: str, failed_prefix: str) -> str:
    if failed_prefix.startswith(base_prefix):
        return failed_prefix[len(base_prefix) :]
    return failed_prefix


def _snippet_for_scope(runtime: ControllerRuntime, scope: Granularity) -> str:
    for region in reversed(runtime.repair_regions):
        if region.scope == scope:
            return runtime.state.prefix[len(region.base_prefix) :]
    return "(empty)"


def _clear_transient_repair(runtime: ControllerRuntime) -> None:
    """Clear per-attempt failure state. Does NOT touch the region stack."""
    runtime.failed_prefix = None
    runtime.failed_assistant_prefix = None
    runtime.failed_extractor_state = None
    runtime.pending_patch = None
    runtime.feedback_parser_error = None


def _pop_repair_regions(runtime: ControllerRuntime, committed_scope: Granularity) -> None:
    """Pop all regions whose scope <= committed_scope."""
    while runtime.repair_regions and runtime.repair_regions[-1].scope <= committed_scope:
        runtime.repair_regions.pop()


def _write_region_start_only(content: AssistantContent | None) -> AssistantContent:
    if content is None or not content.has_begin_marker:
        return AssistantContent.empty()
    return AssistantContent(
        prelude=content.prelude,
        code="",
        postlude="",
        pending_text="",
        has_begin_marker=True,
        region_state=WriteRegionState.INSIDE,
        markers=content.markers,
    )


def _restore_inside_from_anchor(anchor: AssistantContent, code_prefix: str) -> AssistantContent:
    return AssistantContent(
        prelude=anchor.prelude,
        code=code_prefix,
        postlude="",
        pending_text="",
        has_begin_marker=True,
        region_state=WriteRegionState.INSIDE,
        markers=anchor.markers,
    )


def _get_write_anchor(rollback_manager: RollbackManager):
    anchor = getattr(rollback_manager, "write_anchor", None)
    return anchor


def _set_write_anchor(
    rollback_manager: RollbackManager,
    assistant_prefix: AssistantContent,
    extractor_state: OutputExtractorState | None,
) -> None:
    setter = getattr(rollback_manager, "set_write_anchor", None)
    if not callable(setter):
        raise RuntimeError("RollbackManager missing set_write_anchor")
    setter(assistant_prefix, extractor_state)


def _assert_extractor_consistency(runtime: ControllerRuntime) -> None:
    if runtime.extractor_state is None:
        return
    if runtime.extractor_state.segment.state != runtime.assistant_prefix.region_state:
        raise RuntimeError(
            "assistant write-region state diverged from segment parser state "
            f"({runtime.assistant_prefix.region_state} vs {runtime.extractor_state.segment.state})"
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
    while k < len(previous) and k < len(current) and GroupStackFrame.matches(previous[k], current[k]):
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
    rollback_scope: Granularity | None = None,
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


def _render_feedback_assistant(
    assistant_prefix: str | AssistantContent,
    feedback_state: FeedbackState,
    runtime: ControllerRuntime,
    comment_prefix: str = "//",
    excluded_scopes: frozenset[Granularity] = frozenset(),
    format_config: RepairFeedbackFormatConfig | None = None,
) -> str:
    scoped_feedback = tuple(
        row for row in feedback_state.scoped_active_snapshot()
        if row[0] not in excluded_scopes
    )
    if not scoped_feedback:
        if isinstance(assistant_prefix, AssistantContent):
            return assistant_prefix.render()
        return assistant_prefix

    blocks: list[tuple[int | None, str]] = []
    for scope, anchor, outputs in scoped_feedback:
        snippet = _snippet_for_scope(runtime, scope)
        all_diags = tuple(d for o in outputs for d in o.diagnostics)
        region = next((r for r in reversed(runtime.repair_regions) if r.scope == scope), None)
        start_line = _snippet_start_line(region.base_prefix) if region else 1
        snippet = annotate_snippet(snippet, start_line, all_diags, comment_prefix)
        feedback_text = render_repair_feedback(
            RepairContext(
                failed_snippet=snippet,
                repair_scope=scope,
                outputs=outputs,
            ),
            format_config=format_config,
        )
        blocks.append((anchor, feedback_text))

    if isinstance(assistant_prefix, AssistantContent) and (
        assistant_prefix.region_state == WriteRegionState.INSIDE
        or assistant_prefix.has_begin_marker
    ):
        code = assistant_prefix.code
        insertions: list[tuple[int, str]] = []
        for anchor, block in blocks:
            pos = len(code) if anchor is None else max(0, min(anchor, len(code)))
            insertions.append((pos, block))
        insertions.sort(key=lambda item: item[0], reverse=True)
        for pos, block in insertions:
            code = f"{code[:pos]}{block}\n\n{code[pos:]}"
        return assistant_prefix.with_code(code).render()

    rendered_prefix = assistant_prefix.render() if isinstance(assistant_prefix, AssistantContent) else assistant_prefix
    suffix = "\n\n".join(block for _, block in blocks)
    if not rendered_prefix:
        return suffix
    return f"{rendered_prefix}\n\n{suffix}"


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
    comment_prefix: str = "//",
) -> None:
    context.extract_write_region = True
    context.channel = GenerationChannel.CONTINUATION
    active_outputs = feedback_state.active_snapshot()
    if (
        feedback_enabled
        and active_outputs
        and runtime.failed_prefix is not None
        and runtime.current_region is not None
    ):
        runtime.repair_regions.pop()
        _clear_transient_repair(runtime)
    if runtime.extractor_state is None:
        runtime.extractor_state = generator.capture_output_extractor_state()
    _assert_extractor_consistency(runtime)
    generator.restore_output_extractor_state(runtime.extractor_state)
    update_last_assistant(base_messages, runtime.assistant_prefix)
    messages = list(base_messages)
    if (
        feedback_enabled
        and active_outputs
        and not (runtime.failed_prefix is not None and runtime.current_region is not None)
        and runtime.last_feedback_mechanism == FeedbackMechanism.A
        and runtime.last_action != Action.CONTINUE
    ):
        update_last_assistant(
            messages,
            _render_feedback_assistant(
                runtime.assistant_prefix, feedback_state, runtime, comment_prefix,
            ),
        )
    context.messages = messages
    result = generator.generate_step(context)
    runtime.state.prefix += result.delta_text
    assistant_delta = result.assistant_delta or AssistantContent.from_text(result.delta_text)
    runtime.assistant_prefix = merge_assistant_content(runtime.assistant_prefix, assistant_delta)
    runtime.extractor_state = generator.capture_output_extractor_state()
    write_anchor = _get_write_anchor(rollback_manager)
    if write_anchor is None and runtime.assistant_prefix.has_begin_marker:
        anchor_assistant = _write_region_start_only(runtime.assistant_prefix)
        anchor_state = runtime.extractor_state.force_inside() if runtime.extractor_state else None
        _set_write_anchor(rollback_manager, anchor_assistant, anchor_state)
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
                if output.verdict == Verdict.NOT_APPLICABLE and output.diagnostics:
                    logger.info(
                        "oracle_not_applicable: oracle=%s reason=%s",
                        output.oracle_name,
                        _truncate(output.diagnostics[0].message, 800),
                    )
            if feedback_enabled:
                feedback_state.on_verify(outputs, selected_scope=effective_granularity)
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
                _clear_transient_repair(runtime)
    else:
        _clear_transient_repair(runtime)
        runtime.repair_regions.clear()
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
    feedback_state: FeedbackState,
    feedback_enabled: bool,
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
    if feedback_enabled:
        feedback_state.on_commit(runtime.last_verification_granularity)
    if runtime.last_verification_granularity is not None:
        _pop_repair_regions(runtime, runtime.last_verification_granularity)
    _clear_transient_repair(runtime)
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
    write_anchor = _get_write_anchor(rollback_manager)
    if write_anchor is not None:
        runtime.assistant_prefix = _restore_inside_from_anchor(
            write_anchor.assistant_prefix,
            runtime.state.prefix,
        )
        if runtime.extractor_state is None:
            runtime.extractor_state = write_anchor.extractor_state
        if runtime.extractor_state is None:
            runtime.extractor_state = generator.capture_output_extractor_state()
        runtime.extractor_state = runtime.extractor_state.force_inside()
    elif runtime.extractor_state is None:
        runtime.extractor_state = generator.capture_output_extractor_state()
    generator.restore_output_extractor_state(runtime.extractor_state)
    if feedback_enabled:
        feedback_state.on_rollback(op.rollback_scope)
        feedback_state.bind_failures_to_scope(list(runtime.last_outputs), op.rollback_scope)
        while runtime.repair_regions and runtime.repair_regions[-1].scope <= op.rollback_scope:
            runtime.repair_regions.pop()
        runtime.repair_regions.append(
            RepairRegion(
                scope=op.rollback_scope,
                base_prefix=runtime.state.prefix,
                base_assistant_prefix=runtime.assistant_prefix,
                base_extractor_state=runtime.extractor_state,
            )
        )
        runtime.pending_patch = None
        feedback_state.set_scope_anchor(op.rollback_scope, len(runtime.state.prefix))
    else:
        runtime.repair_regions.clear()
        _clear_transient_repair(runtime)
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
    feedback_lang_config: FeedbackLanguageConfig,
    write_region_markers: WriteRegionMarkers,
    trace: list[TraceEvent],
) -> None:
    if (
        runtime.failed_prefix is None
        or runtime.repair_base_prefix is None
        or runtime.repair_base_assistant_prefix is None
        or runtime.repair_base_extractor_state is None
    ):
        raise RuntimeError("FEEDBACK requires failed_prefix and repair base prefix.")
    requested_mechanism = op.feedback_mechanism or FeedbackMechanism.A
    repair_scope = runtime.repair_scope or Granularity.STMT
    mechanism = _select_feedback_mechanism(
        requested_mechanism=requested_mechanism,
        repair_scope=repair_scope,
    )
    current_base = runtime.repair_base_prefix
    # Feedback B lists diagnostics explicitly; annotation would be redundant.
    bad_snippet = _failed_snippet(current_base, runtime.failed_prefix)
    scope_filter = repair_scope
    repair_context = RepairContext.from_feedback_state(
        feedback_state,
        bad_snippet,
        repair_scope=repair_scope,
        scope_filter=scope_filter,
        parser_error_context=runtime.feedback_parser_error,
    )
    feedback_plan = build_feedback_plan(
        mechanism=mechanism,
        repair_context=repair_context,
        repair_feedback_format_config=repair_feedback_format_config,
        lang_config=feedback_lang_config,
        write_region_markers=write_region_markers,
    )
    feedback_strategy = _feedback_strategy_for_mechanism(feedback_plan.mechanism)
    feedback_gen = _select_feedback_generator(
        generator=generator,
        feedback_generator=feedback_generator,
    )
    _prepare_feedback_extractor_state(
        feedback_gen=feedback_gen,
        feedback_plan=feedback_plan,
        repair_base_extractor_state=runtime.repair_base_extractor_state,
    )
    replayed_assistant_prefix = _render_feedback_assistant(
        runtime.repair_base_assistant_prefix,
        feedback_state,
        runtime,
        excluded_scopes=frozenset({repair_scope}),
        format_config=RepairFeedbackFormatConfig(include_failed_snippet=False),
    )
    update_last_assistant(base_messages, replayed_assistant_prefix)

    if feedback_plan.post_region_injection is not None:
        result, total_tokens, patch_response_prefix = _feedback_two_phase(
            feedback_plan=feedback_plan,
            feedback_strategy=feedback_strategy,
            feedback_gen=feedback_gen,
            base_messages=base_messages,
            context=context,
            runtime=runtime,
            feedback_lang_config=feedback_lang_config,
            write_region_markers=write_region_markers,
        )
    else:
        patch_response_prefix = feedback_plan.response_prefix
        context.extract_write_region = feedback_plan.channel == GenerationChannel.CONTINUATION
        context.channel = feedback_plan.channel
        context.messages = feedback_strategy.apply(
            base_messages,
            feedback_plan.prompt,
            replayed_assistant_prefix,
            feedback_plan.response_prefix,
        )
        result = feedback_gen.generate_step(context)
        total_tokens = result.delta_tokens

    generator.restore_output_extractor_state(runtime.repair_base_extractor_state)
    if feedback_plan.channel == GenerationChannel.PATCH:
        patch_text = _render_feedback_patch_text(
            patch_response_prefix,
            result.delta_text,
        )
        parse_result = parse_diff_feedback_output(patch_text, markers=write_region_markers)
        scope = repair_scope
        scope_error = None
        if parse_result.patch is not None:
            scope_error = validate_patch_scope(
                parse_result.patch,
                scope,
                feedback_lang_config,
                rollback_snippet=bad_snippet,
            )
        runtime.pending_patch = parse_result.patch
        runtime.feedback_parser_error = parse_result.error or scope_error
        if runtime.feedback_parser_error is not None:
            logger.warning("feedback patch rejected: %s", runtime.feedback_parser_error)
            runtime.pending_patch = None
    else:
        if feedback_lang_config.is_comment_only(result.delta_text):
            runtime.pending_patch = None
            runtime.feedback_parser_error = "patch is pure comments with no code"
            logger.warning("feedback patch rejected: %s", runtime.feedback_parser_error)
        else:
            runtime.pending_patch = result.delta_text
            runtime.feedback_parser_error = None
    runtime.last_feedback_mechanism = feedback_plan.mechanism
    budget.add_tokens(total_tokens)
    runtime.last_stop_reason = result.stop_reason
    runtime.last_action = Action.FEEDBACK
    patch_len = len(runtime.pending_patch) if runtime.pending_patch is not None else 0
    logger.info(
        "feedback: step=%s mechanism=%s delta_tokens=%s stop_reason=%s patch_len=%s parse_error=%s",
        runtime.state.step,
        feedback_plan.mechanism,
        total_tokens,
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


def _set_stop_on_write_region_open(gen: Generator, enabled: bool) -> None:
    setter = getattr(gen, "set_stop_on_write_region_open", None)
    if callable(setter):
        setter(enabled)


def _feedback_two_phase(
    *,
    feedback_plan: FeedbackPlan,
    feedback_strategy: FeedbackStrategy,
    feedback_gen: Generator,
    base_messages: list[GenerateMessage],
    context: GenerateContext,
    runtime: ControllerRuntime,
    feedback_lang_config: FeedbackLanguageConfig,
    write_region_markers: WriteRegionMarkers,
) -> tuple[GenerateResult, int, AssistantContent]:
    assert feedback_plan.post_region_injection is not None
    base_assistant = (
        runtime.repair_base_assistant_prefix
        or AssistantContent.empty(markers=write_region_markers)
    )

    _set_stop_on_write_region_open(feedback_gen, True)
    context.extract_write_region = True
    context.channel = GenerationChannel.CONTINUATION
    context.messages = feedback_strategy.apply(
        base_messages,
        feedback_plan.prompt,
        base_assistant,
        None,
    )
    phase1 = feedback_gen.generate_step(context)
    _set_stop_on_write_region_open(feedback_gen, False)
    phase1_tokens = phase1.delta_tokens

    reasoning = ""
    if phase1.assistant_delta is not None and phase1.assistant_delta.has_begin_marker:
        reasoning = phase1.assistant_delta.prelude
    else:
        reasoning = phase1.delta_text
    logger.info(
        "feedback_two_phase: phase1 tokens=%s reasoning_len=%s begin_found=%s",
        phase1_tokens,
        len(reasoning),
        phase1.assistant_delta is not None and phase1.assistant_delta.has_begin_marker,
    )

    phase2_prefix = AssistantContent(
        prelude=reasoning,
        code=feedback_plan.post_region_injection,
        has_begin_marker=True,
        region_state=WriteRegionState.INSIDE,
        markers=write_region_markers,
    )
    feedback_gen.reset_output_extractor()
    context.extract_write_region = False
    context.channel = GenerationChannel.PATCH
    context.messages = feedback_strategy.apply(
        base_messages,
        feedback_plan.prompt,
        base_assistant,
        phase2_prefix,
    )
    phase2 = feedback_gen.generate_step(context)
    total_tokens = phase1_tokens + phase2.delta_tokens
    logger.info(
        "feedback_two_phase: phase2 tokens=%s total=%s",
        phase2.delta_tokens,
        total_tokens,
    )
    return phase2, total_tokens, phase2_prefix


def _select_feedback_mechanism(
    *,
    requested_mechanism: FeedbackMechanism,
    repair_scope: Granularity,
) -> FeedbackMechanism:
    if requested_mechanism == FeedbackMechanism.B and repair_scope != Granularity.STMT:
        return FeedbackMechanism.A
    return requested_mechanism


def _render_feedback_patch_text(
    response_prefix: str | AssistantContent | None,
    delta_text: str,
) -> str:
    if response_prefix is None:
        return delta_text
    if isinstance(response_prefix, AssistantContent):
        if response_prefix.has_begin_marker:
            region = f"{response_prefix.markers.begin_marker}\n{response_prefix.code}"
            if response_prefix.has_end_marker:
                region += f"{response_prefix.markers.end_marker}\n"
            return f"{region}{delta_text}"
        return f"{response_prefix.render()}{delta_text}"
    return f"{response_prefix}{delta_text}"


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
    _clear_transient_repair(runtime)
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


# Header line emitted by `_format_bailout_diagnostics` and stripped/matched by
# the experiment runners' outer repair loop. Kept as a module-level constant so
# producer (this module) and consumers (runners) cannot drift.
BAILOUT_DIAGNOSTICS_HEADER = "BAILOUT! Oracle diagnostics:"


def _format_bailout_diagnostics(outputs: tuple[OracleOutput, ...]) -> str:
    """Concatenate per-oracle pre-rendered error blocks into a bailout postlude.

    Reads `OracleOutput.rendered_diagnostics` (parallel to `diagnostics`) so
    each oracle's own format is preserved (rustc's pretty arrows; tsc/eslint's
    line-anchored rich block with hints). Filters to error-level diagnostics.
    """
    blocks: list[str] = []
    for output in outputs:
        for diag, rendered in zip(output.diagnostics, output.rendered_diagnostics):
            if diag.severity != "error" or not rendered:
                continue
            blocks.append(rendered)
    if not blocks:
        return ""
    return BAILOUT_DIAGNOSTICS_HEADER + "\n" + "\n".join(blocks)


def _handle_bailout_terminate(
    runtime: ControllerRuntime,
    write_region_markers: WriteRegionMarkers,
) -> None:
    """Construct a closed assistant message with rendered code and diagnostics.

    Updates runtime.state.prefix to the rendered code and
    runtime.assistant_prefix to the full closed write region with diagnostics.
    """
    rendered_code = (
        runtime.last_artifact.code
        if runtime.last_artifact is not None
        else runtime.state.prefix
    )
    logger.info("bailout_rendered_prefix: len=%s", len(rendered_code))

    diag_text = _format_bailout_diagnostics(runtime.last_outputs)
    diag_count = sum(
        1 for o in runtime.last_outputs
        for d in o.diagnostics if d.severity == "error"
    )
    logger.info("bailout_diagnostics: count=%s", diag_count)

    # Build a properly closed AssistantContent: prelude + BEGIN marker +
    # rendered code + END marker + diagnostics postlude.
    runtime.assistant_prefix = AssistantContent(
        prelude=runtime.assistant_prefix.prelude,
        code=rendered_code,
        postlude=diag_text,
        pending_text="",
        has_begin_marker=True,
        has_end_marker=True,
        region_state=WriteRegionState.OUTSIDE,
        markers=write_region_markers,
    )
    runtime.state.prefix = rendered_code

    logger.info(
        "bailout_terminate: step=%s rendered_prefix_len=%s diagnostics=%s",
        runtime.state.step, len(rendered_code), diag_count,
    )


def _handle_terminate(
    runtime: ControllerRuntime,
    feedback_state: FeedbackState,
    feedback_enabled: bool,
    budget: Budget,
    trace: list[TraceEvent],
    *,
    op: ControllerOp | None = None,
    write_region_markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
) -> None:
    if feedback_enabled:
        feedback_state.on_terminate()
    runtime.repair_regions.clear()
    _clear_transient_repair(runtime)
    is_bailout = op is not None and op.bailout
    if is_bailout:
        _handle_bailout_terminate(runtime, write_region_markers)
    runtime.last_action = Action.TERMINATE
    logger.info("terminate: step=%s", runtime.state.step)
    _append_trace(
        trace,
        step=runtime.state.step,
        stop_reason=runtime.last_stop_reason,
        action=Action.TERMINATE,
        verification_granularity=None,
        budget=budget,
        oracle_outputs=runtime.last_outputs if is_bailout else (),
        notes="bailout" if is_bailout else "",
    )


def run_dtv_loop(
    generator: Generator,
    renderer: Renderer,
    oracles: Sequence[Oracle],
    budget: Budget,
    feedback_state: FeedbackState,
    rollback_manager: RollbackManager,
    policy: Policy,
    feedback_lang_config: FeedbackLanguageConfig,
    feedback_generator: Generator | None = None,
    repair_feedback_format_config: RepairFeedbackFormatConfig | None = None,
    max_steps: int | None = 100,
    max_new_length: int = 1024,
    prompt_prefix: str = "",
    oracle_runner: OracleRunner | None = None,
    write_region_markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
    inject_write_region_contract: bool = True,
    initial_messages: Sequence[GenerateMessage] | None = None,
) -> tuple[str, list[TraceEvent]]:
    """Run the DTV decoding loop.

    Returns (raw_assistant_content, trace):
      - raw_assistant_content: the full assistant message as a string, including
        any write-region markers and (on bailout) appended oracle diagnostics.
        Callers should treat this the same as raw model output.
      - trace: debug-only list of TraceEvent. Use for logging and analysis;
        do NOT use trace for data flow to outer loops or repair prompts.

    State machine actions: GENERATE, VERIFY(granularity), COMMIT,
    ROLLBACK(scope), FEEDBACK, APPLY_PATCH, CONTINUE, TERMINATE.
    """
    if oracle_runner is None:
        oracle_runner = DummyOracleRunner()
    oracle_runner_impl: OracleRunner = oracle_runner
    feedback_enabled = _policy_feedback_enabled(policy)
    policy.reset_round_state()
    if hasattr(rollback_manager, "markers"):
        rollback_manager.markers = write_region_markers

    runtime = ControllerRuntime(state=ControllerState(prefix=""))
    runtime.extractor_state = generator.capture_output_extractor_state()
    trace: list[TraceEvent] = []

    if initial_messages is not None:
        if prompt_prefix:
            raise ValueError("prompt_prefix must be empty when initial_messages are provided")
        if inject_write_region_contract:
            raise ValueError(
                "inject_write_region_contract must be False when initial_messages are provided",
            )
        base_messages = list(initial_messages)
        if not base_messages:
            raise ValueError("initial_messages must not be empty")
    else:
        base_messages = []
        if inject_write_region_contract:
            contract_prompt = render_write_region_contract(feedback_lang_config.name, write_region_markers)
            user_prompt = contract_prompt if not prompt_prefix else f"{prompt_prefix.rstrip()}\n\n{contract_prompt}"
        else:
            user_prompt = prompt_prefix
        base_messages.append(GenerateMessage(role="user", content=user_prompt, stop=True))
        base_messages.append(
            GenerateMessage(role="assistant", content=AssistantContent.empty(markers=write_region_markers), stop=False)
        )
    context = GenerateContext(messages=base_messages, steps=0, max_new_length=max_new_length)

    while max_steps is None or runtime.state.step < max_steps:
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
            repair_scope=runtime.repair_scope,
            write_region_state=generator.get_output_extractor_state(),
        )
        op = policy.next_action(ctx)
        logger.info(
            "policy: step=%s action=%s verification_granularity=%s rollback_scope=%s feedback_mechanism=%s tokens_used=%s tokens_left=%s",
            runtime.state.step,
            op.action,
            op.verification_granularity,
            op.rollback_scope,
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
                comment_prefix=feedback_lang_config.comment_prefix,
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
                oracle_runner_impl,
                budget,
                feedback_state,
                feedback_enabled,
                trace,
            )
            runtime.state.step += 1
            continue

        if op.action == Action.COMMIT:
            _handle_commit(
                runtime,
                rollback_manager,
                feedback_state,
                feedback_enabled,
                budget,
                trace,
            )
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
                feedback_lang_config,
                write_region_markers,
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
            _handle_terminate(
                runtime, feedback_state, feedback_enabled, budget, trace,
                op=op, write_region_markers=write_region_markers,
            )
            break

        raise ValueError(f"Unsupported action: {op.action}")

    return runtime.assistant_prefix.render(), trace
