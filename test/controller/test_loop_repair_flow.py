from __future__ import annotations

from dataclasses import dataclass

from controller.loop import ControllerOp, run_dtv_loop, select_oracles_by_granularity
from core.budget import Budget
from core.llm_output import FenceState
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


@dataclass(frozen=True)
class _OracleFail:
    name: str = "oracle"
    required_granularity: Granularity = Granularity.STMT

    def run(self, state, artifact, context):
        _ = state
        _ = artifact
        _ = context
        from core.types import OracleOutput

        return OracleOutput(
            oracle_name=self.name,
            verdict=Verdict.FAIL,
            diagnostics=(),
            realized_cost=1,
        )


class _SequenceGenerator:
    def __init__(self, steps: list[str]) -> None:
        self.steps = steps
        self.idx = 0

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
        return FenceState.OUTSIDE


class _ToggleRenderer:
    def __init__(self) -> None:
        self.calls = 0

    def try_render(self, prefix: str) -> RenderResult:
        _ = prefix
        self.calls += 1
        if self.calls == 1:
            artifact = Artifact(code=prefix)
            return RenderResult(status=RenderStatus.OK, artifact=artifact)
        return RenderResult(status=RenderStatus.CONTINUE, artifact=None, notes="need more")


class _OkRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        artifact = Artifact(code=prefix)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _RepairFlowPolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        # 0: generate bad stmt
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        # 1: verify -> fail
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        # 2: rollback to base
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=RollbackScope.STMT)
        # 3: probing verify that is inconclusive
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        # 4: feedback should still be possible
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.FEEDBACK)
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


class _ContinueGeneratePolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=RollbackScope.STMT)
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.CONTINUE)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.GENERATE)
        if self.stage == 5:
            return ControllerOp(Action.FEEDBACK)
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


class _NoOraclePolicy:
    def __init__(self) -> None:
        self.stage = 0
        self.allow_oracles = True

    def next_action(self, ctx) -> ControllerOp:
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=RollbackScope.STMT)
        if self.stage == 3:
            self.stage = 4
            self.allow_oracles = False
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 4:
            return ControllerOp(Action.FEEDBACK)
        return ControllerOp(Action.TERMINATE)

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        if self.allow_oracles:
            return select_oracles_by_granularity(
                artifact,
                budget,
                available,
                selection_granularity=selection_granularity,
            )
        return []


def test_failed_context_survives_inconclusive_verify() -> None:
    generator = _SequenceGenerator(["bad stmt\n", "fix\n"])
    renderer = _ToggleRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=8)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _RepairFlowPolicy()

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

    assert any(event.action == Action.FEEDBACK for event in trace)


def test_continue_then_generate_keeps_failed_context() -> None:
    generator = _SequenceGenerator(["bad stmt\n", "fix\n"])
    renderer = _OkRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=8)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _ContinueGeneratePolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        max_steps=7,
    )

    assert any(event.action == Action.FEEDBACK for event in trace)


def test_failed_context_survives_no_oracle_verify() -> None:
    generator = _SequenceGenerator(["bad stmt\n", "fix\n"])
    renderer = _OkRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=8)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _NoOraclePolicy()

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

    assert any(event.action == Action.FEEDBACK for event in trace)
