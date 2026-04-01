from __future__ import annotations

from dataclasses import dataclass

import pytest

from c_rust.feedback import RUST_FEEDBACK_LANG
from core.llm_output import AssistantContent, FenceParserSnapshot, FenceState, OutputExtractorState
from core.types import TestCase, TranslationSample
from controller.loop import ControllerOp, run_dtv_loop, select_oracles_by_granularity
from core.budget import Budget
from core.types import (
    Action,
    Artifact,
    Diagnostic,
    GenerateContext,
    GenerateResult,
    Granularity,
    GroupEvent,
    GroupEventAction,
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
class _FakeGenerator:
    code: str

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        return GenerateResult(
            delta_text=self.code,
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
        )

    def reset_output_extractor(self) -> None:
        return None

    def get_output_extractor_state(self) -> FenceState:
        return FenceState.OUTSIDE

    def capture_output_extractor_state(self) -> OutputExtractorState:
        snapshot = FenceParserSnapshot(state=FenceState.OUTSIDE, saw_fence=False)
        return OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        _ = state


class _DummyRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        artifact = Artifact(code=prefix)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _GroupStackRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        artifact = Artifact(
            code=prefix,
            group_stack=(GroupStackFrame(kind=Granularity.FUNC),),
            group_events=(GroupEvent(action=GroupEventAction.OPEN, kind=Granularity.BLOCK),),
        )
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _FunctionCloseRenderer:
    def __init__(self, sample: TranslationSample, function_name: str) -> None:
        self.sample = sample
        self.function_name = function_name
        self.calls = 0

    def try_render(self, prefix: str) -> RenderResult:
        self.calls += 1
        if self.calls == 1:
            group_stack = (GroupStackFrame(kind=Granularity.FUNC, name_id=self.function_name),)
            group_events: tuple[GroupEvent, ...] = ()
        else:
            group_stack = ()
            group_events = (GroupEvent(action=GroupEventAction.CLOSE, kind=Granularity.FUNC),)
        artifact = Artifact(
            code=prefix,
            sample=self.sample,
            group_stack=group_stack,
            group_events=group_events,
        )
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _SequenceGenerator:
    def __init__(self, steps: list[str]) -> None:
        self.steps = steps
        self.idx = 0
        snapshot = FenceParserSnapshot(state=FenceState.OUTSIDE, saw_fence=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        if self.idx >= len(self.steps):
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="empty"),
            )
        delta = self.steps[self.idx]
        self.idx += 1
        return GenerateResult(
            delta_text=delta,
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
        )

    def reset_output_extractor(self) -> None:
        return None

    def get_output_extractor_state(self) -> FenceState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._extractor_state = state


def _last_assistant_text(context: GenerateContext) -> str:
    for message in reversed(context.messages):
        role = getattr(message, "role", "")
        if role != "assistant":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, AssistantContent):
            return content.render()
        return str(content)
    return ""


class _TrackingGenerator:
    def __init__(self, results: list[GenerateResult]) -> None:
        self.results = results
        self.idx = 0
        self.reset_calls = 0
        self.seen_assistant_messages: list[str] = []
        self.restored_states: list[OutputExtractorState] = []
        snapshot = FenceParserSnapshot(state=FenceState.OUTSIDE, saw_fence=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        self.seen_assistant_messages.append(_last_assistant_text(context))
        if self.idx >= len(self.results):
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="empty"),
            )
        result = self.results[self.idx]
        self.idx += 1
        assistant_delta = result.assistant_delta
        if assistant_delta is not None:
            snapshot = FenceParserSnapshot(
                state=assistant_delta.fence_state,
                saw_fence=bool(assistant_delta.fence_lang) or self._extractor_state.extract.saw_fence,
            )
            self._extractor_state = OutputExtractorState(
                segment=snapshot,
                extract=snapshot,
                shared=snapshot,
                warning_emitted=self._extractor_state.warning_emitted,
            )
        return result

    def reset_output_extractor(self) -> None:
        self.reset_calls += 1

    def get_output_extractor_state(self) -> FenceState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self.restored_states.append(state)
        self._extractor_state = state


class _ScopeFailOracle:
    required_granularity = Granularity.PROGRAM

    def __init__(self, scope: Granularity) -> None:
        self.name = f"fail_{scope.value}"
        self.rollback_scope = scope

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        _ = context
        return OracleOutput(
            oracle_name=self.name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="scope mismatch"),),
            realized_cost=1,
            rollback_scope=self.rollback_scope,
        )


class _RollbackScopePolicy:
    def __init__(self, scope: Granularity) -> None:
        self.scope = scope
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.PROGRAM)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=self.scope)
        return ControllerOp(Action.TERMINATE)

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


class _ProgramFailOracle:
    name = "program_diff"
    required_granularity = Granularity.PROGRAM
    rollback_scope = Granularity.PROGRAM

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        _ = context
        return OracleOutput(
            oracle_name=self.name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="program mismatch"),),
            realized_cost=1,
        )


class _ProgramRollbackThenGeneratePolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.PROGRAM)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.PROGRAM)
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.GENERATE)
        return ControllerOp(Action.TERMINATE)

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


class _SingleStepPolicy:
    def next_action(self, ctx) -> ControllerOp:
        if ctx.last_action is None:
            return ControllerOp(Action.GENERATE)
        if ctx.last_action == Action.GENERATE:
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if ctx.last_action == Action.VERIFY:
            if any(out.verdict == Verdict.FAIL for out in ctx.last_outputs):
                return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
            if ctx.last_outputs and all(out.verdict == Verdict.PASS for out in ctx.last_outputs):
                return ControllerOp(Action.COMMIT)
            return ControllerOp(Action.CONTINUE)
        if ctx.last_action in {Action.COMMIT, Action.ROLLBACK}:
            return ControllerOp(Action.TERMINATE)
        return ControllerOp(Action.GENERATE)

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


class _PassOracle:
    name = "pass"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        _ = context
        return OracleOutput(oracle_name=self.name, verdict=Verdict.PASS)


class _FunctionNameOracle:
    name = "function_diff"
    required_granularity = Granularity.FUNC
    rollback_scope = Granularity.FUNC

    def __init__(self, expected: str) -> None:
        self.expected = expected

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        function_name = context.closed_function_name
        verdict = Verdict.PASS if function_name == self.expected else Verdict.FAIL
        return OracleOutput(oracle_name=self.name, verdict=verdict)


class _FunctionClosePolicy:
    def __init__(self) -> None:
        self.phase = 0

    def next_action(self, ctx) -> ControllerOp:
        if ctx.last_action is None:
            return ControllerOp(Action.GENERATE)
        if ctx.last_action == Action.GENERATE:
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.FUNC)
        if ctx.last_action == Action.VERIFY:
            if self.phase == 0:
                self.phase = 1
                return ControllerOp(Action.GENERATE)
            return ControllerOp(Action.COMMIT)
        if ctx.last_action == Action.COMMIT:
            return ControllerOp(Action.TERMINATE)
        return ControllerOp(Action.TERMINATE)

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        _ = selection_granularity
        if self.phase == 0:
            return []
        return available


def test_function_oracle_receives_closed_function_name() -> None:
    sample = TranslationSample(
        source_code="int foo(){return 1;}",
        source_lang="c",
        test_cases=[TestCase(stdin="")],
    )
    generator = _SequenceGenerator(["fn foo() {\n", "}\n"])
    renderer = _FunctionCloseRenderer(sample, "foo")
    oracles = [_FunctionNameOracle("foo")]
    budget = Budget(gen_tokens_budget=4)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _FunctionClosePolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=6,
    )

    assert any(
        event.action == Action.VERIFY
        and any(
            output.oracle_name == "function_diff" and output.verdict == Verdict.PASS
            for output in event.oracle_outputs
        )
        for event in trace
    )


def test_commit_prefers_group_stack_over_events() -> None:
    generator = _FakeGenerator(code="let x = 1;\n")
    renderer = _GroupStackRenderer()
    oracles = [_PassOracle()]
    budget = Budget(gen_tokens_budget=4)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _SingleStepPolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=4,
    )

    assert trace
    assert trace[-2].action == Action.COMMIT
    assert [(f.kind, f.start_stmt) for f in rollback_manager.group_stack] == [(Granularity.FUNC, 0)]


@pytest.mark.parametrize(
    "scope",
    [
        Granularity.STMT,
        Granularity.BLOCK,
        Granularity.FUNC,
        Granularity.PROGRAM,
    ],
)
def test_rollback_restores_inside_parser_state_for_all_scopes(scope: Granularity) -> None:
    generator = _TrackingGenerator(
        [
            GenerateResult(
                delta_text="bad\n",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
                assistant_delta=AssistantContent(
                    pre_fence="Rust translation follows:\n",
                    fence_lang="rust",
                    code="bad\n",
                    fence_state=FenceState.INSIDE,
                ),
            ),
        ]
    )
    renderer = _DummyRenderer()
    oracles = [_ScopeFailOracle(scope)]
    budget = Budget(gen_tokens_budget=8)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _RollbackScopePolicy(scope)

    run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=5,
    )

    assert rollback_manager.fence_anchor is not None
    assert rollback_manager.fence_anchor.assistant_prefix.pre_fence == "Rust translation follows:\n"
    assert generator.restored_states
    restored = generator.restored_states[-1]
    assert restored.extract.state == FenceState.INSIDE
    assert restored.extract.saw_fence


def test_program_rollback_then_generate_abandons_feedback_payload() -> None:
    generator = _TrackingGenerator(
        [
            GenerateResult(
                delta_text="bad\n",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
                assistant_delta=AssistantContent(
                    pre_fence="Here is the Rust translation:\n",
                    fence_lang="rust",
                    code="bad\n",
                    fence_state=FenceState.INSIDE,
                ),
            ),
            GenerateResult(
                delta_text="good\n",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
                assistant_delta=AssistantContent(
                    pre_fence="Here is the Rust translation:\n",
                    fence_lang="rust",
                    code="good\n",
                    fence_state=FenceState.INSIDE,
                ),
            ),
        ]
    )
    renderer = _DummyRenderer()
    oracles = [_ProgramFailOracle()]
    budget = Budget(gen_tokens_budget=8)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _ProgramRollbackThenGeneratePolicy()

    output, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=6,
    )

    assert output == "good\n"
    assert [event.action for event in trace] == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.GENERATE,
        Action.TERMINATE,
    ]
    assert rollback_manager.fence_anchor is not None
    assert rollback_manager.fence_anchor.assistant_prefix.pre_fence == "Here is the Rust translation:\n"
    assert generator.reset_calls == 0
    assert generator.restored_states
    assert generator.restored_states[-1].extract.state == FenceState.INSIDE
