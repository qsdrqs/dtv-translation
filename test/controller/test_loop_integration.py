from __future__ import annotations

from dataclasses import dataclass

from c_rust.oracles import RustcOracle
from core.llm_output import FenceState
from core.types import TestCase, TranslationSample
from c_rust.render import CRustRenderer
from controller.loop import ControllerOp, run_dtv_loop, select_oracles_by_granularity
from core.budget import Budget
from core.types import (
    Action,
    Artifact,
    GenerateContext,
    GenerateResult,
    Granularity,
    GroupEvent,
    GroupEventAction,
    GroupStackFrame,
    OracleOutput,
    RenderResult,
    RenderStatus,
    RollbackScope,
    StopReason,
    Verdict,
)
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager
from test.c_rust.utils import _rustc_path


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
        return FenceState.OUTSIDE


class _SingleStepPolicy:
    def next_action(self, ctx) -> ControllerOp:
        if ctx.last_action is None:
            return ControllerOp(Action.GENERATE)
        if ctx.last_action == Action.GENERATE:
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if ctx.last_action == Action.VERIFY:
            if any(out.verdict == Verdict.FAIL for out in ctx.last_outputs):
                return ControllerOp(Action.ROLLBACK, rollback_scope=RollbackScope.STMT)
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


class _TwoStepPolicy:
    def __init__(self) -> None:
        self.phase = 0

    def next_action(self, ctx) -> ControllerOp:
        if ctx.last_action is None:
            return ControllerOp(Action.GENERATE)
        if ctx.last_action == Action.GENERATE:
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if ctx.last_action == Action.VERIFY:
            if self.phase == 0:
                self.phase += 1
                return ControllerOp(Action.COMMIT)
            return ControllerOp(Action.ROLLBACK, rollback_scope=RollbackScope.STMT)
        if ctx.last_action == Action.COMMIT:
            return ControllerOp(Action.GENERATE)
        if ctx.last_action == Action.ROLLBACK:
            return ControllerOp(Action.TERMINATE)
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


class _PassOracle:
    name = "pass"
    required_granularity = Granularity.STMT

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        _ = context
        return OracleOutput(oracle_name=self.name, verdict=Verdict.PASS)


class _FunctionNameOracle:
    name = "function_diff"
    required_granularity = Granularity.FUNC

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


def test_loop_commits_with_rustc_oracle() -> None:
    _rustc_path()
    code = "fn foo() -> i32 { 1 }\n"
    generator = _FakeGenerator(code=code)
    renderer = _DummyRenderer()
    oracles = [RustcOracle(timeout_s=5.0)]
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
        max_steps=4,
    )

    assert trace
    assert trace[-2].action == Action.COMMIT
    assert any(
        output.oracle_name == "rustc" and output.verdict == Verdict.PASS
        for output in trace[-2].oracle_outputs
    )
    assert budget.oracle_calls.get("rustc") == 1
    assert len(rollback_manager.stmt_checkpoints) == 1


def test_loop_rolls_back_when_rustc_fail() -> None:
    _rustc_path()
    code = "fn foo() { let x = ; }\n"
    generator = _FakeGenerator(code=code)
    renderer = _DummyRenderer()
    oracles = [RustcOracle(timeout_s=5.0)]
    budget = Budget(gen_tokens_budget=4)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _SingleStepPolicy()

    final_prefix, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        max_steps=4,
    )

    assert trace
    assert trace[-2].action == Action.ROLLBACK
    assert any(
        output.oracle_name == "rustc" and output.verdict == Verdict.FAIL
        for output in trace[-3].oracle_outputs
    )
    assert final_prefix == ""



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
        max_steps=4,
    )

    assert trace
    assert trace[-2].action == Action.COMMIT
    assert [(f.kind, f.start_stmt) for f in rollback_manager.group_stack] == [(Granularity.FUNC, 0)]



def test_loop_rolls_back_to_previous_checkpoint() -> None:
    _rustc_path()
    step1 = """\
fn foo() -> i32 {
  let a = 1;
  if a == 0 {
    let b = 2;
"""
    step2 = """\
    return "str here";
"""
    generator = _SequenceGenerator([step1, step2])
    renderer = CRustRenderer()
    oracles = [RustcOracle(timeout_s=5.0)]
    budget = Budget(gen_tokens_budget=4)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _TwoStepPolicy()

    final_prefix, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        max_steps=6,
    )

    assert trace
    assert any(event.action == Action.COMMIT for event in trace)
    assert any(event.action == Action.ROLLBACK for event in trace)
    assert final_prefix == step1
    assert len(rollback_manager.stmt_checkpoints) == 1
