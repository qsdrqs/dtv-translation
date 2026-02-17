from __future__ import annotations

from dataclasses import dataclass

from c_rust.oracles import RustcOracle
from c_rust.render import CRustRenderer
from controller.loop import ControllerOp, run_dtv_loop, select_oracles_by_granularity
from core.budget import Budget
from core.llm_output import FenceParserSnapshot, FenceState, OutputExtractorState
from core.types import (
    Action,
    Artifact,
    GenerateContext,
    GenerateResult,
    Granularity,
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
        _ = context
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
        _ = context
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


class _GenerateVerifyTerminatePolicy:
    def next_action(self, ctx) -> ControllerOp:
        if ctx.last_action is None:
            return ControllerOp(Action.GENERATE)
        if ctx.last_action == Action.GENERATE:
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
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


def test_loop_incomplete_use_item_returns_continue_without_oracle_runs() -> None:
    _rustc_path()
    generator = _FakeGenerator(code="use std::io::{self, Read}")
    renderer = CRustRenderer()
    oracles = [RustcOracle(timeout_s=5.0)]
    budget = Budget(gen_tokens_budget=4)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _GenerateVerifyTerminatePolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        max_steps=3,
    )

    verify_events = [event for event in trace if event.action == Action.VERIFY]
    assert len(verify_events) == 1
    verify_event = verify_events[0]
    assert verify_event.render_status == RenderStatus.CONTINUE
    assert verify_event.oracle_outputs == ()
    assert "render_continue:cursor_incomplete" in verify_event.notes
