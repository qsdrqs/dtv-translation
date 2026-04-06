from __future__ import annotations

from c_rust.feedback import RUST_FEEDBACK_LANG
from controller.loop import ControllerOp, run_dtv_loop
from core.budget import Budget
from core.llm_output import OutputExtractorState, WriteRegionParserSnapshot, WriteRegionState
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


class _NoWriteRegionGenerator:
    def __init__(self) -> None:
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        _ = context
        return GenerateResult(
            delta_text="",
            delta_tokens=1,
            stop_reason=StopReason(kind="no_write_region_eos"),
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


def test_run_loop_no_write_region_eos_delegates_to_policy() -> None:
    """no_write_region_eos no longer short-circuits the loop; the policy decides."""
    budget = Budget(gen_tokens_budget=4)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()

    _, trace = run_dtv_loop(
        generator=_NoWriteRegionGenerator(),
        renderer=_DummyRenderer(),
        oracles=[],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=_GenerateOnlyPolicy(),
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=2,
    )

    # The loop runs until max_steps; policy gets to decide (no short-circuit).
    actions = [e.action for e in trace]
    assert Action.TERMINATE not in actions
    assert actions[0] == Action.GENERATE
