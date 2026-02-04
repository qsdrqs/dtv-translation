from __future__ import annotations

from controller.loop import ControllerOp, run_dtv_loop
from core.budget import Budget
from core.llm_output import FenceState
from core.types import (
    Action,
    Artifact,
    GenerateContext,
    GenerateResult,
    RenderResult,
    RenderStatus,
    StopReason,
)
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


class _NoFenceGenerator:
    def generate_step(self, context: GenerateContext) -> GenerateResult:
        _ = context
        return GenerateResult(
            delta_text="",
            delta_tokens=1,
            stop_reason=StopReason(kind="no_fence_eos"),
        )

    def reset_output_extractor(self) -> None:
        return None

    def get_output_extractor_state(self) -> FenceState:
        return FenceState.OUTSIDE


class _DummyRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        artifact = Artifact(code=prefix)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _GenerateOnlyPolicy:
    def next_action(self, ctx) -> ControllerOp:
        if ctx.last_action is None:
            return ControllerOp(Action.GENERATE)
        return ControllerOp(Action.CONTINUE)

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        _ = selection_granularity
        _ = artifact
        _ = budget
        _ = available
        return []


def test_run_loop_terminates_on_no_fence_eos() -> None:
    budget = Budget(gen_tokens_budget=4)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()

    _, trace = run_dtv_loop(
        generator=_NoFenceGenerator(),
        renderer=_DummyRenderer(),
        oracles=[],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=_GenerateOnlyPolicy(),
        max_steps=2,
    )

    assert trace[-1].action == Action.TERMINATE
