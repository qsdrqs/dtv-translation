from __future__ import annotations

from dataclasses import dataclass

import pytest

from c_rust.feedback import RUST_FEEDBACK_LANG
from controller.loop import _format_bailout_diagnostics, run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from core.budget import Budget
from core.llm_output import AssistantContent, OutputExtractorState, WriteRegionParserSnapshot, WriteRegionState
from core.types import (
    Action,
    Artifact,
    Diagnostic,
    FeedbackMechanism,
    GenerateContext,
    GenerateResult,
    Granularity,
    GroupStackFrame,
    OracleOutput,
    RenderResult,
    RenderStatus,
    Granularity,
    StopReason,
    Verdict,
)
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


@dataclass(frozen=True)
class _Step:
    text: str
    stop_reason: StopReason
    tokens: int = 1
    write_region_state: WriteRegionState | None = None


class _SequenceGenerator:
    def __init__(self, steps: list[_Step]) -> None:
        self.steps = steps
        self.idx = 0
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        _ = context
        if self.idx >= len(self.steps):
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="empty"),
            )
        step = self.steps[self.idx]
        self.idx += 1
        if step.write_region_state is not None:
            snap = WriteRegionParserSnapshot(
                state=step.write_region_state,
                saw_begin=step.write_region_state == WriteRegionState.INSIDE,
                saw_end=step.write_region_state == WriteRegionState.OUTSIDE and self._extractor_state.extract.saw_begin,
            )
            self._extractor_state = OutputExtractorState(
                segment=snap, extract=snap, shared=snap, warning_emitted=False,
            )
        elif step.stop_reason.kind == "write_region_closed":
            done = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=True, saw_end=True)
            self._extractor_state = OutputExtractorState(
                segment=done, extract=done, shared=done, warning_emitted=False,
            )
        return GenerateResult(
            delta_text=step.text,
            delta_tokens=step.tokens,
            stop_reason=step.stop_reason,
        )

    def reset_output_extractor(self) -> None:
        return None

    def get_output_extractor_state(self) -> WriteRegionState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._extractor_state = state

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        _ = enabled


class _FeedbackRestoreOrderGenerator:
    def __init__(self) -> None:
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )
        self._generated_once = False
        self.events: list[str] = []

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        if self._is_feedback_context(context):
            self.events.append(f"generate_feedback:{int(self._extractor_state.warning_emitted)}")
            return GenerateResult(
                delta_text="good;",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
            )
        self.events.append(f"generate_regular:{int(self._extractor_state.warning_emitted)}")
        if self._generated_once:
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="empty"),
            )
        self._generated_once = True
        inside = WriteRegionParserSnapshot(state=WriteRegionState.INSIDE, saw_begin=True, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=inside,
            extract=inside,
            shared=inside,
            warning_emitted=True,
        )
        return GenerateResult(
            delta_text="bad;",
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
            assistant_delta=AssistantContent(
                code="bad;",
                has_begin_marker=True,
                region_state=WriteRegionState.INSIDE,
            ),
        )

    def reset_output_extractor(self) -> None:
        self.events.append("reset")

    def get_output_extractor_state(self) -> WriteRegionState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self.events.append(f"restore:{int(state.warning_emitted)}")
        self._extractor_state = state

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        _ = enabled

    @staticmethod
    def _is_feedback_context(context: GenerateContext) -> bool:
        for message in reversed(context.messages):
            role = getattr(message, "role", "")
            if role != "assistant":
                continue
            content = getattr(message, "content", "")
            text = content.render() if isinstance(content, AssistantContent) else str(content)
            if "/* repair feedback:" in text:
                return True
        return False


class _MechanismBInsideGenerator:
    def __init__(self) -> None:
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )
        self._generated_once = False
        self._feedback_phase = 0
        self.feedback_states: list[WriteRegionState] = []

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        if self._is_mechanism_b_feedback_context(context):
            self.feedback_states.append(self._extractor_state.extract.state)
            self._feedback_phase += 1
            if self._feedback_phase == 1:
                return GenerateResult(
                    delta_text="Let me reason about this.\n",
                    delta_tokens=1,
                    stop_reason=StopReason(kind="boundary"),
                )
            return GenerateResult(
                delta_text="good;\n<<END_WRITE_CODE>>\n",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
            )
        if self._generated_once:
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="empty"),
            )
        self._generated_once = True
        inside = WriteRegionParserSnapshot(state=WriteRegionState.INSIDE, saw_begin=True, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=inside,
            extract=inside,
            shared=inside,
            warning_emitted=False,
        )
        return GenerateResult(
            delta_text="bad;",
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
            assistant_delta=AssistantContent(
                code="bad;",
                has_begin_marker=True,
                region_state=WriteRegionState.INSIDE,
            ),
        )

    def reset_output_extractor(self) -> None:
        return None

    def get_output_extractor_state(self) -> WriteRegionState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._extractor_state = state

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        _ = enabled

    @staticmethod
    def _is_mechanism_b_feedback_context(context: GenerateContext) -> bool:
        for message in reversed(context.messages):
            role = getattr(message, "role", "")
            if role != "user":
                continue
            text = str(getattr(message, "content", ""))
            if "The previous generated next code snippet was:" in text:
                return True
        return False


class _OkRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        artifact = Artifact(code=prefix)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _SequenceRenderer:
    def __init__(self, statuses: list[RenderStatus]) -> None:
        self.statuses = statuses
        self.calls = 0

    def try_render(self, prefix: str) -> RenderResult:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        if status == RenderStatus.OK:
            artifact = Artifact(code=prefix)
            return RenderResult(status=status, artifact=artifact)
        return RenderResult(status=status, artifact=None, notes="mock")


class _BlockCloseRenderer:
    def __init__(self) -> None:
        self.calls = 0

    def try_render(self, prefix: str) -> RenderResult:
        self.calls += 1
        if self.calls == 1:
            group_stack = (GroupStackFrame(kind=Granularity.BLOCK),)
        else:
            group_stack = ()
        artifact = Artifact(code=prefix, group_stack=group_stack)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _StaticGroupStackRenderer:
    def __init__(self, group_stack: tuple[GroupStackFrame, ...]) -> None:
        self.group_stack = group_stack

    def try_render(self, prefix: str) -> RenderResult:
        artifact = Artifact(code=prefix, group_stack=self.group_stack)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _SequenceOracle:
    def __init__(
        self,
        verdicts: list[Verdict],
        *,
        name: str = "oracle",
        required_granularity: Granularity = Granularity.STMT,
        rollback_scope: Granularity | None = None,
    ) -> None:
        self.verdicts = verdicts
        self.name = name
        self.required_granularity = required_granularity
        self.rollback_scope = rollback_scope if rollback_scope is not None else Granularity(required_granularity.value)
        self.idx = 0

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        _ = context
        if not self.verdicts:
            verdict = Verdict.NOT_APPLICABLE
        else:
            verdict = self.verdicts[min(self.idx, len(self.verdicts) - 1)]
        self.idx += 1
        diagnostics = ()
        rendered: tuple[str, ...] = ()
        if verdict == Verdict.FAIL:
            diagnostics = (Diagnostic(message="Test failed", severity="error"),)
            rendered = ("- rendered: Test failed",)
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=diagnostics,
            rendered_diagnostics=rendered,
            realized_cost=1,
        )


def _run_loop(generator, renderer, oracles, policy, max_steps: int) -> tuple[str, list]:
    budget = Budget(gen_tokens_budget=16)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    return run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=max_steps,
    )


def _format_trace_for_observation(trace: list) -> str:
    lines = ["Trace events:"]
    for event in trace:
        verify_scope = "-"
        if event.verification_granularity is not None:
            verify_scope = event.verification_granularity.value
        rollback_scope = "-"
        if event.rollback_scope is not None:
            rollback_scope = event.rollback_scope.value
        stop_reason = "-"
        if event.stop_reason is not None:
            stop_reason = event.stop_reason.kind
        lines.append(
            f"  step={event.step:02d} action={event.action.value:<9} "
            f"verify={verify_scope:<7} rollback={rollback_scope:<7} stop={stop_reason}"
        )
    rollback_sequence = [
        event.rollback_scope.value
        for event in trace
        if event.action == Action.ROLLBACK and event.rollback_scope is not None
    ]
    lines.append(f"Rollback sequence: {rollback_sequence}")
    return "\n".join(lines)


def test_default_policy_pass_commits() -> None:
    generator = _SequenceGenerator([
        _Step("let x = 1;", StopReason(kind="boundary")),
    ])
    renderer = _OkRenderer()
    oracles = [_SequenceOracle([Verdict.PASS])]
    policy = DefaultPolicy()

    final_prefix, trace = _run_loop(generator, renderer, oracles, policy, max_steps=3)

    actions = [event.action for event in trace]
    assert actions == [Action.GENERATE, Action.VERIFY, Action.COMMIT]
    assert final_prefix == "let x = 1;"


def test_default_policy_retry_after_fail_without_feedback_retries_generate() -> None:
    generator = _SequenceGenerator([
        _Step("bad;", StopReason(kind="boundary")),
        _Step("good;", StopReason(kind="boundary")),
    ])
    renderer = _OkRenderer()
    oracles = [_SequenceOracle([Verdict.FAIL, Verdict.PASS])]
    policy = DefaultPolicy(DefaultPolicyConfig(enable_feedback=False))

    final_prefix, trace = _run_loop(generator, renderer, oracles, policy, max_steps=6)

    actions = [event.action for event in trace]
    assert actions == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.GENERATE,
        Action.VERIFY,
        Action.COMMIT,
    ]
    assert final_prefix == "good;"


def test_default_policy_no_oracles_without_close_stays_in_continue_loop() -> None:
    generator = _SequenceGenerator([
        _Step("let x = 1;", StopReason(kind="boundary")),
        _Step("let y = 2;", StopReason(kind="eos")),
    ])
    renderer = _OkRenderer()
    oracles = [_SequenceOracle([Verdict.PASS], required_granularity=Granularity.PROGRAM)]
    policy = DefaultPolicy()

    final_prefix, trace = _run_loop(generator, renderer, oracles, policy, max_steps=6)

    actions = [event.action for event in trace]
    assert actions == [
        Action.GENERATE,
        Action.VERIFY,
        Action.CONTINUE,
        Action.GENERATE,
        Action.VERIFY,
        Action.CONTINUE,
    ]
    assert final_prefix == "let x = 1;let y = 2;"


def test_default_policy_block_boundary_skips_stmt_oracle() -> None:
    generator = _SequenceGenerator([
        _Step("let x = 1;", StopReason(kind="boundary")),
        _Step("}", StopReason(kind="boundary")),
    ])
    renderer = _BlockCloseRenderer()
    oracles = [
        _SequenceOracle([Verdict.PASS], name="stmt", required_granularity=Granularity.STMT),
        _SequenceOracle([Verdict.PASS], name="block", required_granularity=Granularity.BLOCK),
    ]
    policy = DefaultPolicy(DefaultPolicyConfig(boundary_granularity=Granularity.BLOCK))

    _, trace = _run_loop(generator, renderer, oracles, policy, max_steps=6)

    verify_events = [event for event in trace if event.action == Action.VERIFY]
    assert verify_events
    assert all(
        output.oracle_name != "stmt"
        for event in verify_events
        for output in event.oracle_outputs
    )
    assert any(
        output.oracle_name == "block"
        for event in verify_events
        for output in event.oracle_outputs
    )


def test_default_policy_inconclusive_render_continue_then_generate() -> None:
    generator = _SequenceGenerator([
        _Step("let x = 1;", StopReason(kind="boundary")),
        _Step("let y = 2;", StopReason(kind="boundary")),
    ])
    renderer = _SequenceRenderer([RenderStatus.CONTINUE, RenderStatus.OK])
    oracles = [_SequenceOracle([Verdict.PASS])]
    policy = DefaultPolicy()

    final_prefix, trace = _run_loop(generator, renderer, oracles, policy, max_steps=6)

    actions = [event.action for event in trace]
    assert actions == [
        Action.GENERATE,
        Action.VERIFY,
        Action.CONTINUE,
        Action.GENERATE,
        Action.VERIFY,
        Action.COMMIT,
    ]
    assert trace[1].render_status == RenderStatus.CONTINUE
    assert trace[4].render_status == RenderStatus.OK
    assert final_prefix == "let x = 1;let y = 2;"


def test_default_policy_eos_no_oracles_commits() -> None:
    generator = _SequenceGenerator([
        _Step("fn main() {}", StopReason(kind="write_region_closed")),
    ])
    renderer = _OkRenderer()
    policy = DefaultPolicy()

    final_prefix, trace = _run_loop(generator, renderer, [], policy, max_steps=100)

    actions = [event.action for event in trace]
    assert actions == [Action.GENERATE, Action.VERIFY, Action.COMMIT, Action.TERMINATE]
    assert final_prefix == "fn main() {}"


def test_default_policy_repair_flow_commits() -> None:
    generator = _SequenceGenerator([
        _Step("bad;", StopReason(kind="boundary")),
        _Step("good;", StopReason(kind="boundary")),
    ])
    renderer = _OkRenderer()
    oracles = [_SequenceOracle([Verdict.FAIL, Verdict.PASS])]
    policy = DefaultPolicy()

    final_prefix, trace = _run_loop(generator, renderer, oracles, policy, max_steps=7)

    actions = [event.action for event in trace]
    assert actions == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.VERIFY,
        Action.COMMIT,
    ]
    assert final_prefix == "good;"


def test_default_policy_force_b_feedback_flows_through_loop() -> None:
    generator = _MechanismBInsideGenerator()
    renderer = _OkRenderer()
    oracles = [_SequenceOracle([Verdict.FAIL, Verdict.PASS])]
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            feedback_force_mechanism=FeedbackMechanism.B,
            max_repair_rounds=2,
        )
    )

    final_prefix, trace = _run_loop(generator, renderer, oracles, policy, max_steps=7)

    actions = [event.action for event in trace]
    assert actions == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.VERIFY,
        Action.COMMIT,
    ]
    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 1
    assert feedback_events[0].notes == "feedback_mechanism=b"
    assert generator.feedback_states == [WriteRegionState.INSIDE, WriteRegionState.INSIDE]
    assert "good;" in final_prefix


def test_default_policy_inline_feedback_restores_extractor_before_generation() -> None:
    generator = _FeedbackRestoreOrderGenerator()
    renderer = _OkRenderer()
    oracles = [_SequenceOracle([Verdict.FAIL, Verdict.PASS])]
    policy = DefaultPolicy(DefaultPolicyConfig(max_repair_rounds=2))

    final_prefix, trace = _run_loop(generator, renderer, oracles, policy, max_steps=7)

    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 1
    assert feedback_events[0].notes == "feedback_mechanism=a"
    feedback_idx = generator.events.index("generate_feedback:1")
    assert generator.events[feedback_idx - 1] == "restore:1"
    assert generator.events[feedback_idx + 1] == "restore:1"
    assert "good;" in final_prefix


class _AlwaysBadFeedbackGenerator:
    """First call returns 'ok;' (for COMMIT checkpoint), all subsequent return 'bad;'."""

    def __init__(self) -> None:
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot, extract=snapshot, shared=snapshot, warning_emitted=False,
        )
        self._first = True

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        if self._first:
            self._first = False
            inside = WriteRegionParserSnapshot(state=WriteRegionState.INSIDE, saw_begin=True, saw_end=False)
            self._extractor_state = OutputExtractorState(
                segment=inside, extract=inside, shared=inside, warning_emitted=False,
            )
            return GenerateResult(
                delta_text="ok;",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
                assistant_delta=AssistantContent(
                    code="ok;", has_begin_marker=True, region_state=WriteRegionState.INSIDE,
                ),
            )
        return GenerateResult(
            delta_text="bad;",
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
        )

    def reset_output_extractor(self) -> None:
        return None

    def get_output_extractor_state(self) -> WriteRegionState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._extractor_state = state

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        _ = enabled


def _run_stall_escalation_test(group_stack, expected_escalation_scope):
    generator = _AlwaysBadFeedbackGenerator()
    renderer = _StaticGroupStackRenderer(group_stack)
    oracles = [_SequenceOracle([Verdict.PASS] + [Verdict.FAIL] * 20)]
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=True,
        stmt_stall_max_retries_before_escalation=3,
        feedback_max_a_rounds_per_key=10,
    ))
    budget = Budget(gen_tokens_budget=32)
    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(),
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=30,
    )
    actions = [event.action for event in trace]
    assert actions[:3] == [Action.GENERATE, Action.VERIFY, Action.COMMIT]
    rollback_scopes = [event.rollback_scope for event in trace if event.action == Action.ROLLBACK]
    assert len(rollback_scopes) >= 4, f"expected >= 4 rollbacks, got {len(rollback_scopes)}"
    assert rollback_scopes[:3] == [Granularity.STMT] * 3
    assert rollback_scopes[3] == expected_escalation_scope

    # FEEDBACK and APPLY_PATCH must appear (production path, not no-feedback path).
    assert Action.FEEDBACK in actions
    assert Action.APPLY_PATCH in actions


def test_default_policy_e2e_stmt_stall_escalates_to_block_scope() -> None:
    _run_stall_escalation_test(
        group_stack=(
            GroupStackFrame(kind=Granularity.FUNC),
            GroupStackFrame(kind=Granularity.BLOCK),
        ),
        expected_escalation_scope=Granularity.BLOCK,
    )


def test_default_policy_e2e_stmt_stall_escalates_to_func_without_block_scope() -> None:
    _run_stall_escalation_test(
        group_stack=(GroupStackFrame(kind=Granularity.FUNC),),
        expected_escalation_scope=Granularity.FUNC,
    )


# bailout execution logic tests


def test_format_bailout_diagnostics_error_only() -> None:
    outputs = (
        OracleOutput(
            oracle_name="tsc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="mismatched types", severity="error", error_code="E0308"),
                Diagnostic(message="consider adding a type", severity="warning"),
            ),
            rendered_diagnostics=(
                "- L1:1 | let x: i32 = \"hi\";\n    error: mismatched types (E0308)",
                "    warning: consider adding a type",
            ),
        ),
        OracleOutput(
            oracle_name="eslint",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="missing annotation", severity="error"),
            ),
            rendered_diagnostics=(
                "- L2:5 | function bar(arg) {}\n    error: missing annotation\n    hint: Add an explicit type annotation",
            ),
        ),
    )
    result = _format_bailout_diagnostics(outputs)
    expected = (
        "BAILOUT! Oracle diagnostics:\n"
        "- L1:1 | let x: i32 = \"hi\";\n    error: mismatched types (E0308)\n"
        "- L2:5 | function bar(arg) {}\n    error: missing annotation\n    hint: Add an explicit type annotation"
    )
    assert result == expected


def test_format_bailout_diagnostics_empty_when_no_errors() -> None:
    outputs = (
        OracleOutput(
            oracle_name="tsc",
            verdict=Verdict.PASS,
            diagnostics=(
                Diagnostic(message="unused var", severity="warning"),
            ),
            rendered_diagnostics=(
                "- L1:1 | let x = 1;\n    warning: unused var",
            ),
        ),
    )
    assert _format_bailout_diagnostics(outputs) == ""


def test_format_bailout_diagnostics_empty_when_rendered_missing() -> None:
    """OracleOutput without rendered_diagnostics produces no bailout postlude.

    Defensive contract: zip over parallel tuples; missing rendered tuple
    means nothing to surface even if Diagnostic objects exist.
    """
    outputs = (
        OracleOutput(
            oracle_name="tsc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="mismatched types", severity="error", error_code="E0308"),
            ),
        ),
    )
    assert _format_bailout_diagnostics(outputs) == ""


class _SuffixAppendingRenderer:
    def __init__(self, suffix: str = "\n// rendered") -> None:
        self.suffix = suffix

    def try_render(self, prefix: str) -> RenderResult:
        artifact = Artifact(code=prefix + self.suffix)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _AlwaysFailOracle:
    name = "test_oracle"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def __init__(self, diagnostics: tuple[Diagnostic, ...] = ()) -> None:
        self._diagnostics = diagnostics or (
            Diagnostic(message="type mismatch", severity="error", error_code="TS2322"),
        )
        self._rendered = tuple(
            f"- error: {d.message} ({d.error_code})" if d.error_code else f"- error: {d.message}"
            for d in self._diagnostics
        )

    def run(self, state, artifact, context) -> OracleOutput:
        return OracleOutput(
            oracle_name=self.name,
            verdict=Verdict.FAIL,
            diagnostics=self._diagnostics,
            rendered_diagnostics=self._rendered,
            realized_cost=1,
        )


def test_bailout_terminate_returns_rendered_code_in_raw_output() -> None:
    generator = _SequenceGenerator([
        _Step("let x = 1;", StopReason(kind="boundary")),
    ])
    renderer = _SuffixAppendingRenderer(suffix="\n// rendered")
    oracle = _AlwaysFailOracle()
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=False,
        bailout_visit_threshold=1,
    ))
    raw_output, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[oracle],
        budget=Budget(gen_tokens_budget=16),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(),
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=20,
    )
    assert "let x = 1;\n// rendered" in raw_output
    assert "BAILOUT! Oracle diagnostics:" in raw_output
    actions = [e.action for e in trace]
    assert Action.TERMINATE in actions


def test_normal_terminate_returns_raw_assistant_content() -> None:
    generator = _SequenceGenerator([
        _Step("let x = 1;", StopReason(kind="write_region_closed"),
              write_region_state=WriteRegionState.OUTSIDE),
    ])
    renderer = _OkRenderer()
    oracle = _SequenceOracle([Verdict.PASS])
    policy = DefaultPolicy()
    raw_output, trace = _run_loop(generator, renderer, [oracle], policy, max_steps=20)
    assert "let x = 1;" in raw_output
    actions = [e.action for e in trace]
    assert Action.TERMINATE in actions


def test_bailout_terminate_includes_diagnostics_in_raw_output() -> None:
    diags = (
        Diagnostic(message="bad type", severity="error", error_code="E0308"),
    )
    generator = _SequenceGenerator([
        _Step("bad;", StopReason(kind="boundary")),
    ])
    renderer = _OkRenderer()
    oracle = _AlwaysFailOracle(diagnostics=diags)
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=False,
        bailout_visit_threshold=1,
    ))
    raw_output, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[oracle],
        budget=Budget(gen_tokens_budget=16),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(),
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=20,
    )
    assert "bad;" in raw_output
    assert "E0308" in raw_output
    assert "bad type" in raw_output
    actions = [e.action for e in trace]
    assert Action.TERMINATE in actions
