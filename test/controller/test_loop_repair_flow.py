from __future__ import annotations

import pytest

from c_rust.feedback import RUST_FEEDBACK_LANG
from controller.loop import ControllerOp, run_dtv_loop, select_oracles_by_granularity
from core.budget import Budget
from core.llm_output import AssistantContent, FenceParserSnapshot, FenceState, OutputExtractorState
from core.types import (
    Action,
    Artifact,
    FeedbackMechanism,
    GenerateContext,
    GenerateResult,
    Granularity,
    RenderResult,
    RenderStatus,
    Granularity,
    StopReason,
    Verdict,
)
from feedback.formatter import RepairFeedbackFormatConfig
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


class _OracleFail:
    name = "oracle"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def run(self, state, artifact, context):
        _ = state
        _ = artifact
        _ = context
        from core.types import Diagnostic, OracleOutput

        return OracleOutput(
            oracle_name=self.name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="test failure"),),
            realized_cost=1,
        )


class _OracleFailThenPass:
    name = "oracle"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def __init__(self) -> None:
        self.calls = 0

    def run(self, state, artifact, context):
        _ = state
        _ = artifact
        _ = context
        from core.types import Diagnostic, OracleOutput

        self.calls += 1
        verdict = Verdict.FAIL if self.calls == 1 else Verdict.PASS
        diagnostics = ()
        if verdict == Verdict.FAIL:
            diagnostics = (Diagnostic(message="test failure"),)
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=diagnostics,
            realized_cost=1,
        )


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


def _last_assistant_text(context: GenerateContext) -> str:
    for message in reversed(context.messages):
        if getattr(message, "role", "") != "assistant":
            continue
        return str(getattr(message, "content", ""))
    return ""


def _last_user_text(context: GenerateContext) -> str:
    for message in reversed(context.messages):
        if getattr(message, "role", "") != "user":
            continue
        return str(getattr(message, "content", ""))
    return ""


class _TrackingSequenceGenerator(_SequenceGenerator):
    def __init__(self, steps: list[str]) -> None:
        super().__init__(steps)
        self.seen_assistant_messages: list[str] = []
        self.seen_user_messages: list[str] = []

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        self.seen_assistant_messages.append(_last_assistant_text(context))
        self.seen_user_messages.append(_last_user_text(context))
        return super().generate_step(context)


class _FencedTrackingGenerator:
    def __init__(self, steps: list[str]) -> None:
        self.steps = steps
        self.idx = 0
        self.seen_assistant_messages: list[str] = []
        self.seen_user_messages: list[str] = []
        snapshot = FenceParserSnapshot(state=FenceState.OUTSIDE, saw_fence=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        self.seen_assistant_messages.append(_last_assistant_text(context))
        self.seen_user_messages.append(_last_user_text(context))
        if self.idx >= len(self.steps):
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="empty"),
                assistant_delta=AssistantContent.empty(),
            )
        delta = self.steps[self.idx]
        self.idx += 1
        inside = FenceParserSnapshot(state=FenceState.INSIDE, saw_fence=True)
        self._extractor_state = OutputExtractorState(
            segment=inside,
            extract=inside,
            shared=inside,
            warning_emitted=False,
        )
        assistant_delta = AssistantContent(
            pre_fence="",
            fence_lang="rust",
            code=delta,
            post_fence="",
            pending_text="",
            fence_state=FenceState.INSIDE,
        )
        return GenerateResult(
            delta_text=delta,
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
            assistant_delta=assistant_delta,
        )

    def reset_output_extractor(self) -> None:
        snapshot = FenceParserSnapshot(state=FenceState.OUTSIDE, saw_fence=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def get_output_extractor_state(self) -> FenceState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._extractor_state = state


class _TokenSequenceGenerator:
    def __init__(self, steps: list[tuple[str, int]]) -> None:
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
        delta_text, delta_tokens = self.steps[self.idx]
        self.idx += 1
        return GenerateResult(
            delta_text=delta_text,
            delta_tokens=delta_tokens,
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
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
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


class _GenerateFeedbackApplyTerminatePolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.APPLY_PATCH)
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
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
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
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
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


class _MechanismBApplyPolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.B)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.APPLY_PATCH)
        if self.stage == 5:
            self.stage = 6
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


class _MechanismBRetryPolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
        if self.stage in {3, 4}:
            self.stage += 1
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.B)
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


class _ScopeSequencedOracle:
    def __init__(
        self,
        *,
        name: str,
        required_granularity: Granularity,
        rollback_scope: Granularity,
        verdicts: list[Verdict],
        message: str,
    ) -> None:
        self.name = name
        self.required_granularity = required_granularity
        self.rollback_scope = rollback_scope
        self._verdicts = verdicts
        self._idx = 0
        self._message = message

    def run(self, state, artifact, context):
        _ = state
        _ = artifact
        _ = context
        from core.types import Diagnostic, OracleOutput

        if self._idx >= len(self._verdicts):
            verdict = self._verdicts[-1]
        else:
            verdict = self._verdicts[self._idx]
        self._idx += 1
        diagnostics = ()
        if verdict == Verdict.FAIL:
            diagnostics = (Diagnostic(message=self._message),)
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=diagnostics,
            realized_cost=1,
            rollback_scope=self.rollback_scope,
        )


class _ScopeAwareFeedbackPolicy:
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
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.APPLY_PATCH)
        if self.stage == 5:
            self.stage = 6
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 6:
            self.stage = 7
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
        if self.stage == 7:
            self.stage = 8
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A)
        if self.stage == 8:
            self.stage = 9
            return ControllerOp(Action.APPLY_PATCH)
        if self.stage == 9:
            self.stage = 10
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 10:
            self.stage = 11
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.PROGRAM)
        if self.stage == 11:
            self.stage = 12
            return ControllerOp(Action.COMMIT)
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


class _ScopeAwareFeedbackMechanismBPolicy:
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
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.B)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.APPLY_PATCH)
        if self.stage == 5:
            self.stage = 6
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 6:
            self.stage = 7
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
        if self.stage == 7:
            self.stage = 8
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.B)
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


class _GenerateUsesActiveFeedbackPolicy:
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
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.COMMIT)
        if self.stage == 4:
            self.stage = 5
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


class _FeedbackThenGeneratePolicy:
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
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.APPLY_PATCH)
        if self.stage == 5:
            self.stage = 6
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 6:
            self.stage = 7
            return ControllerOp(Action.COMMIT)
        if self.stage == 7:
            self.stage = 8
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


class _FeedbackBThenGeneratePolicy:
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
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.B)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.APPLY_PATCH)
        if self.stage == 5:
            self.stage = 6
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 6:
            self.stage = 7
            return ControllerOp(Action.COMMIT)
        if self.stage == 7:
            self.stage = 8
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


class _StmtLiftToFuncThenGeneratePolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        if self.stage == 0:
            self.stage = 1
            return ControllerOp(Action.GENERATE)
        if self.stage == 1:
            self.stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 2:
            self.stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.FUNC)
        if self.stage == 3:
            self.stage = 4
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A)
        if self.stage == 4:
            self.stage = 5
            return ControllerOp(Action.APPLY_PATCH)
        if self.stage == 5:
            self.stage = 6
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self.stage == 6:
            self.stage = 7
            return ControllerOp(Action.COMMIT)
        if self.stage == 7:
            self.stage = 8
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
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=6,
    )

    assert any(event.action == Action.FEEDBACK for event in trace)


def test_llm_token_accounting_counts_generate_and_feedback_only() -> None:
    generator = _TokenSequenceGenerator(
        [
            ("bad stmt\n", 3),
            ("fixed stmt\n", 5),
        ]
    )
    renderer = _OkRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=16)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _GenerateFeedbackApplyTerminatePolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=8,
    )

    actions = [event.action for event in trace]
    assert actions == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.TERMINATE,
    ]
    assert budget.gen_tokens_used == 8
    feedback_event = next(event for event in trace if event.action == Action.FEEDBACK)
    apply_patch_event = next(event for event in trace if event.action == Action.APPLY_PATCH)
    assert feedback_event.budget_snapshot["gen_tokens_used"] == 8
    assert apply_patch_event.budget_snapshot["gen_tokens_used"] == 8


def test_continue_then_generate_abandons_feedback_payload() -> None:
    generator = _SequenceGenerator(["bad stmt\n", "fix\n"])
    renderer = _OkRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=8)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _ContinueGeneratePolicy()

    output, trace = run_dtv_loop(
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

    assert output == "fix\n"
    assert [event.action for event in trace] == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.CONTINUE,
        Action.GENERATE,
    ]


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
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=6,
    )

    assert any(event.action == Action.FEEDBACK for event in trace)


def test_feedback_prompt_can_omit_failed_snippet() -> None:
    generator = _TrackingSequenceGenerator(["bad stmt\n", "fix\n"])
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
        feedback_lang_config=RUST_FEEDBACK_LANG,
        repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=False),
        max_steps=6,
    )

    assert any(event.action == Action.FEEDBACK for event in trace)
    assert generator.seen_assistant_messages
    feedback_prompt = generator.seen_assistant_messages[-1]
    assert "diagnostics:" in feedback_prompt
    assert "failed snippet:" not in feedback_prompt


def test_structured_feedback_mechanism_b_applies_parsed_patch() -> None:
    # Two-phase feedback B: Phase 1 = reasoning + fence open, Phase 2 = replacement code.
    generator = _SequenceGenerator(["bad stmt\n", "Let me think about this fix.\n```rust\n", "good;\n```\n"])
    renderer = _OkRenderer()
    oracles = [_OracleFailThenPass()]
    budget = Budget(gen_tokens_budget=16)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _MechanismBApplyPolicy()

    final_prefix, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=8,
    )

    actions = [event.action for event in trace]
    assert actions == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.VERIFY,
        Action.TERMINATE,
    ]
    assert trace[3].notes == "feedback_mechanism=b"
    assert final_prefix == "good;"


def test_structured_feedback_mechanism_b_malformed_diff_feeds_next_round() -> None:
    # Round 1 Phase 2: injection provides "- bad stmt\n+ ", model continues with
    # "first;\nsecond;\n" -- the "second;" line lacks a +/- prefix, so the diff
    # parser rejects the patch. Round 2 prompt includes this parse error.
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "Let me try this fix.\n```rust\n",
            "first;\nsecond;\n```\n",
            "Reasoning about the fix.\n```rust\n",
            "fixed;\n```\n",
        ]
    )
    renderer = _OkRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=16)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _MechanismBRetryPolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=7,
    )

    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 2
    assert all(event.notes == "feedback_mechanism=b" for event in feedback_events)
    assert "The previous generated next code snippet was:" in generator.seen_user_messages[1]
    assert generator.seen_user_messages[-1].count("Previous parse error:") == 1
    assert "patch must be a unified diff" in generator.seen_user_messages[-1]


def test_structured_feedback_mechanism_b_scope_validator_failure_feeds_next_round() -> None:
    # Two-phase feedback B: each round = Phase 1 (reasoning + fence open) + Phase 2 (diff code).
    # Round 1 Phase 2: multi-line diff producing a function_item (scope-invalid at STMT).
    # Round 2 Phase 2: valid single-line replacement.
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "Let me wrap this in a function.\n```rust\n",
            "fn main() {\n+     let x: i32 = 1;\n+ }\n```\n",
            "Let me try a simpler fix.\n```rust\n",
            "fixed;\n```\n",
        ]
    )
    renderer = _OkRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=16)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _MechanismBRetryPolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=7,
    )

    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 2
    assert all(event.notes == "feedback_mechanism=b" for event in feedback_events)
    assert Action.APPLY_PATCH not in [event.action for event in trace]
    assert generator.seen_user_messages[-1].count("Previous parse error:") == 1
    assert "stmt-scope patch cannot include top-level items (function_item)" in generator.seen_user_messages[-1]


def test_scope_aware_feedback_retains_per_oracle_entries_until_owner_clears() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "func patch\n",
            "stmt patch\n",
        ]
    )
    renderer = _OkRenderer()
    func_oracle = _ScopeSequencedOracle(
        name="program_oracle",
        required_granularity=Granularity.PROGRAM,
        rollback_scope=Granularity.PROGRAM,
        verdicts=[Verdict.FAIL, Verdict.PASS],
        message="program mismatch",
    )
    stmt_oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.FAIL, Verdict.FAIL, Verdict.PASS, Verdict.PASS],
        message="statement mismatch",
    )
    budget = Budget(gen_tokens_budget=24)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _ScopeAwareFeedbackPolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[stmt_oracle, func_oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=16,
    )

    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 2
    feedback_prompts = generator.seen_assistant_messages[1:]
    assert len(feedback_prompts) == 2
    assert "oracle=program_oracle" in feedback_prompts[0]
    assert "oracle=stmt_oracle" in feedback_prompts[0]
    assert "oracle=program_oracle" in feedback_prompts[1]
    assert "oracle=stmt_oracle" in feedback_prompts[1]

    final_feedback_lines = feedback_state.encode().splitlines()
    assert final_feedback_lines == []


def test_feedback_b_filters_diagnostics_to_current_repair_scope() -> None:
    # First feedback: PROGRAM scope -> B downgraded to A (inline continuation).
    # Second feedback: STMT scope -> B stays B (two-phase).
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "program_fix;\n",
            "Thinking about the stmt fix.\n```rust\n",
            "stmt_fix;\n```\n",
        ]
    )
    renderer = _OkRenderer()
    program_oracle = _ScopeSequencedOracle(
        name="program_oracle",
        required_granularity=Granularity.PROGRAM,
        rollback_scope=Granularity.PROGRAM,
        verdicts=[Verdict.FAIL],
        message="program mismatch",
    )
    stmt_oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.FAIL, Verdict.FAIL, Verdict.PASS, Verdict.PASS],
        message="statement mismatch",
    )
    budget = Budget(gen_tokens_budget=24)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _ScopeAwareFeedbackMechanismBPolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[stmt_oracle, program_oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=16,
    )

    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 2
    assert feedback_events[0].notes == "feedback_mechanism=a"
    assert feedback_events[1].notes == "feedback_mechanism=b"
    # Mechanism A: diagnostics appear in the assistant message (inline format).
    first_feedback_prompt = generator.seen_assistant_messages[1]
    assert "oracle=program_oracle" in first_feedback_prompt
    assert "program mismatch" in first_feedback_prompt
    assert "oracle=stmt_oracle" in first_feedback_prompt
    assert "statement mismatch" in first_feedback_prompt
    # Mechanism B: diagnostics appear in the user message (Phase 1).
    second_feedback_prompt = generator.seen_user_messages[2]
    assert "[stmt_oracle] statement mismatch" in second_feedback_prompt


def test_generate_without_feedback_a_does_not_inject_active_feedback() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "more\n",
        ]
    )
    renderer = _OkRenderer()
    program_oracle = _ScopeSequencedOracle(
        name="program_oracle",
        required_granularity=Granularity.PROGRAM,
        rollback_scope=Granularity.PROGRAM,
        verdicts=[Verdict.FAIL],
        message="program mismatch",
    )
    stmt_oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.PASS],
        message="unused",
    )
    budget = Budget(gen_tokens_budget=16)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _GenerateUsesActiveFeedbackPolicy()

    run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[stmt_oracle, program_oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=12,
    )

    assert len(generator.seen_assistant_messages) == 2
    assert "repair feedback" not in generator.seen_assistant_messages[0]
    prompt = generator.seen_assistant_messages[1]
    assert "bad stmt" in prompt
    assert "/* repair feedback:" not in prompt
    assert "oracle=program_oracle" not in prompt


def test_generate_keeps_feedback_anchor_position_after_feedback_a() -> None:
    generator = _FencedTrackingGenerator(
        [
            "bad stmt\n",
            "use std::io::{self, Write};\n",
            "next;\n",
        ]
    )
    renderer = _OkRenderer()
    program_oracle = _ScopeSequencedOracle(
        name="program_oracle",
        required_granularity=Granularity.PROGRAM,
        rollback_scope=Granularity.PROGRAM,
        verdicts=[Verdict.FAIL],
        message="program mismatch",
    )
    stmt_oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.PASS],
        message="unused",
    )
    budget = Budget(gen_tokens_budget=24)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _FeedbackThenGeneratePolicy()

    run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[stmt_oracle, program_oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=16,
    )

    assert len(generator.seen_assistant_messages) == 3
    feedback_prompt = generator.seen_assistant_messages[1]
    generate_prompt = generator.seen_assistant_messages[2]
    assert "/* repair feedback:" in feedback_prompt
    assert "oracle=program_oracle" in feedback_prompt
    assert "/* repair feedback:" in generate_prompt
    assert "oracle=program_oracle" in generate_prompt
    assert "use std::io::{self, Write};\n" in generate_prompt
    assert generate_prompt.find("/* repair feedback:") < generate_prompt.find("use std::io::{self, Write};\n")


def test_generate_skips_inline_feedback_after_feedback_b() -> None:
    # Two-phase feedback B: Phase 1 (reasoning + fence open) + Phase 2 (replacement).
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "Reasoning about the fix.\n```rust\n",
            "let x = 1;\n```\n",
            "next stmt\n",
        ]
    )
    renderer = _OkRenderer()
    program_oracle = _ScopeSequencedOracle(
        name="program_oracle",
        required_granularity=Granularity.PROGRAM,
        rollback_scope=Granularity.PROGRAM,
        verdicts=[Verdict.FAIL],
        message="program mismatch",
    )
    stmt_oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.PASS],
        message="unused",
    )
    budget = Budget(gen_tokens_budget=24)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _FeedbackBThenGeneratePolicy()

    run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[stmt_oracle, program_oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=16,
    )

    assert len(generator.seen_assistant_messages) == 4
    feedback_user_prompt = generator.seen_user_messages[1]
    generate_prompt = generator.seen_assistant_messages[3]
    assert "The previous generated next code snippet was:" in feedback_user_prompt
    assert "/* repair feedback:" not in generate_prompt


class _BlockRollbackThenCommitThenRefeedbackPolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        actions = [
            ControllerOp(Action.GENERATE),                                      # 0: generate "bad"
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),  # 1: verify -> fail
            ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.BLOCK),  # 2: block rollback
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),  # 3: feedback A
            ControllerOp(Action.APPLY_PATCH),                                   # 4: apply patch
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),  # 5: verify -> pass
            ControllerOp(Action.COMMIT),                                        # 6: commit (STMT)
            ControllerOp(Action.GENERATE),                                      # 7: generate "bad again"
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),  # 8: verify -> fail
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),  # 9: feedback A again
            ControllerOp(Action.TERMINATE),
        ]
        if self.stage >= len(actions):
            return ControllerOp(Action.TERMINATE)
        op = actions[self.stage]
        self.stage += 1
        return op

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


def test_block_rollback_repair_context_survives_stmt_commit() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "patched stmt\n",
            "still bad stmt\n",
            "final fix\n",
        ]
    )
    renderer = _OkRenderer()
    oracle = _ScopeSequencedOracle(
        name="oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.FAIL, Verdict.PASS, Verdict.FAIL],
        message="const assignment error",
    )
    budget = Budget(gen_tokens_budget=24)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _BlockRollbackThenCommitThenRefeedbackPolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=14,
    )

    # The second FEEDBACK (step 9) must succeed, proving repair context
    # survived the STMT commit after BLOCK rollback.
    feedback_events = [e for e in trace if e.action == Action.FEEDBACK]
    assert len(feedback_events) == 2, (
        f"Expected 2 FEEDBACK events (before and after STMT commit), "
        f"got {len(feedback_events)}"
    )

    # Step 7 GENERATE must see inline feedback with a real snippet
    # (the code generated since the BLOCK region base), not "(empty)".
    generate_after_commit = generator.seen_assistant_messages[2]
    assert "failed snippet:" in generate_after_commit
    assert "patched stmt" in generate_after_commit


class _DualHintPolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        actions = [
            ControllerOp(Action.GENERATE),                                      # 0: gen "bad1"
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),  # 1: fail (hint1)
            ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.BLOCK),  # 2: block rollback
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),  # 3: feedback hint1
            ControllerOp(Action.APPLY_PATCH),                                   # 4: apply
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),  # 5: pass
            ControllerOp(Action.COMMIT),                                        # 6: commit STMT
            ControllerOp(Action.GENERATE),                                      # 7: gen "bad2"
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),  # 8: fail (hint2)
            ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT),   # 9: stmt rollback
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),  # 10: feedback hint2
            ControllerOp(Action.APPLY_PATCH),                                   # 11: apply
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),  # 12: pass
            ControllerOp(Action.COMMIT),                                        # 13: commit STMT
            ControllerOp(Action.TERMINATE),
        ]
        if self.stage >= len(actions):
            return ControllerOp(Action.TERMINATE)
        op = actions[self.stage]
        self.stage += 1
        return op

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


def test_dual_hint_block_survives_stmt_repair_cycle() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad1\n",       # step 0: initial gen
            "fix1\n",       # step 3: feedback patch for hint1
            "bad2\n",       # step 7: gen new stmt
            "fix2\n",       # step 10: feedback patch for hint2
        ]
    )
    renderer = _OkRenderer()
    block_oracle = _ScopeSequencedOracle(
        name="block_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.BLOCK,
        verdicts=[Verdict.FAIL, Verdict.PASS, Verdict.FAIL, Verdict.PASS],
        message="block-level error",
    )
    stmt_oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.PASS, Verdict.PASS, Verdict.FAIL, Verdict.PASS],
        message="stmt-level error",
    )
    budget = Budget(gen_tokens_budget=32)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _DualHintPolicy()

    _, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[block_oracle, stmt_oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=20,
    )

    feedback_events = [e for e in trace if e.action == Action.FEEDBACK]
    assert len(feedback_events) == 2

    commit_events = [e for e in trace if e.action == Action.COMMIT]
    assert len(commit_events) == 2

    # Both FEEDBACK events must have produced non-empty patches,
    # proving the repair context was available for both the BLOCK
    # repair (step 3) and the nested STMT repair (step 10).
    for fe in feedback_events:
        assert fe.notes == "" or "rejected" not in fe.notes

    # The second COMMIT (step 13) must not carry block_oracle FAIL
    # in its oracle outputs (block_oracle passed at step 12).
    # But the BLOCK repair region must have survived both STMT commits,
    # which is proven by the second FEEDBACK succeeding at step 10 -
    # it could only work if repair_base_prefix from the BLOCK region
    # was still alive after the first STMT commit at step 6.
    last_commit = commit_events[-1]
    assert last_commit.oracle_outputs is not None
    assert all(o.verdict == Verdict.PASS for o in last_commit.oracle_outputs)

    # Step 10 FEEDBACK(A) snippet must include "fix1" (committed earlier
    # inside the BLOCK region), not just "bad2" (the latest STMT failure).
    # seen_assistant_messages[3] is the 4th generate_step call (step 10 FEEDBACK).
    feedback_hint2_prompt = generator.seen_assistant_messages[3]
    snippet_start = feedback_hint2_prompt.index("failed snippet:")
    snippet_section = feedback_hint2_prompt[snippet_start:]
    assert "fix1" in snippet_section
    assert "bad2" in snippet_section


def test_stmt_failure_lifted_to_func_persists_feedback_through_stmt_commit() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            "fixed stmt\n",
            "next stmt\n",
        ]
    )
    renderer = _OkRenderer()
    stmt_oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.FAIL, Verdict.PASS],
        message="statement mismatch",
    )
    budget = Budget(gen_tokens_budget=24)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _StmtLiftToFuncThenGeneratePolicy()

    run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[stmt_oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=12,
    )

    assert len(generator.seen_assistant_messages) == 3
    feedback_prompt = generator.seen_assistant_messages[1]
    generate_prompt = generator.seen_assistant_messages[2]
    assert "/* repair feedback:" in feedback_prompt
    assert "oracle=stmt_oracle" in feedback_prompt
    assert "/* repair feedback:" in generate_prompt
    assert "oracle=stmt_oracle" in generate_prompt
    assert "statement mismatch" in generate_prompt


class _FuncRollbackRetryThenGeneratePolicy:
    """FUNC rollback where the first repair attempt fails, triggering an
    intermediate STMT rollback before the retry succeeds.

    Flow:
     0: GENERATE
     1: VERIFY(STMT) -> FAIL
     2: ROLLBACK(FUNC)
     3: FEEDBACK(A)            -- first repair attempt
     4: APPLY_PATCH
     5: VERIFY(STMT) -> FAIL   -- attempt fails
     6: ROLLBACK(STMT)          -- intermediate STMT rollback
     7: FEEDBACK(A)            -- retry
     8: APPLY_PATCH
     9: VERIFY(STMT) -> PASS   -- retry succeeds
    10: COMMIT
    11: GENERATE               -- must still carry FUNC-level feedback
    """

    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        actions = [
            ControllerOp(Action.GENERATE),
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),
            ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.FUNC),
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),
            ControllerOp(Action.APPLY_PATCH),
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),
            ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT),
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),
            ControllerOp(Action.APPLY_PATCH),
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),
            ControllerOp(Action.COMMIT),
            ControllerOp(Action.GENERATE),
            ControllerOp(Action.TERMINATE),
        ]
        if self.stage >= len(actions):
            return ControllerOp(Action.TERMINATE)
        op = actions[self.stage]
        self.stage += 1
        return op

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


class _NestedStmtRepairWithinFuncSessionPolicy:
    def __init__(self) -> None:
        self.stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        actions = [
            ControllerOp(Action.GENERATE),
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),
            ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.FUNC),
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),
            ControllerOp(Action.APPLY_PATCH),
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),
            ControllerOp(Action.COMMIT),
            ControllerOp(Action.GENERATE),
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),
            ControllerOp(Action.COMMIT),
            ControllerOp(Action.GENERATE),
            ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT),
            ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT),
            ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.A),
            ControllerOp(Action.TERMINATE),
        ]
        if self.stage >= len(actions):
            return ControllerOp(Action.TERMINATE)
        op = actions[self.stage]
        self.stage += 1
        return op

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


def test_stmt_feedback_uses_innermost_stmt_base_within_func_session() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "seed_stmt\n",
            "func_repair_stmt\n",
            "committed_stmt\n",
            "failing_stmt\n",
            "stmt_retry\n",
        ]
    )
    renderer = _OkRenderer()
    oracle = _ScopeSequencedOracle(
        name="oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.FAIL, Verdict.PASS, Verdict.PASS, Verdict.FAIL],
        message="type error",
    )
    budget = Budget(gen_tokens_budget=40)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _NestedStmtRepairWithinFuncSessionPolicy()

    run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=20,
    )

    # 5 generate_step calls: steps 0, 3, 7, 10, 13
    assert len(generator.seen_assistant_messages) == 5

    stmt_feedback_prompt = generator.seen_assistant_messages[4]
    assert "/* repair feedback:" in stmt_feedback_prompt
    snippet_start = stmt_feedback_prompt.index("failed snippet:\n") + len("failed snippet:\n")
    snippet_end = stmt_feedback_prompt.index("\n\ndiagnostics:", snippet_start)
    failed_snippet = stmt_feedback_prompt[snippet_start:snippet_end]
    assert failed_snippet == "failing_stmt", (
        "nested STMT feedback must slice failed_snippet from the innermost "
        "STMT rollback base, not from the outer FUNC session base"
    )


def test_func_feedback_survives_intermediate_stmt_rollback() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",       # step 0: initial gen
            "still bad\n",      # step 3: first repair (will fail verify)
            "fixed stmt\n",     # step 7: retry (will pass verify)
            "next stmt\n",      # step 11: generate after commit
        ]
    )
    renderer = _OkRenderer()
    oracle = _ScopeSequencedOracle(
        name="stmt_oracle",
        required_granularity=Granularity.STMT,
        rollback_scope=Granularity.STMT,
        verdicts=[Verdict.FAIL, Verdict.FAIL, Verdict.PASS],
        message="statement mismatch",
    )
    budget = Budget(gen_tokens_budget=32)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _FuncRollbackRetryThenGeneratePolicy()

    run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=[oracle],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=16,
    )

    # 4 generate_step calls: steps 0, 3, 7, 11
    assert len(generator.seen_assistant_messages) == 4

    generate_prompt = generator.seen_assistant_messages[3]
    assert "/* repair feedback:" in generate_prompt, (
        "FUNC-level feedback comment must survive an intermediate "
        "ROLLBACK(STMT) within the FUNC repair; "
        "bind_failures_to_scope._drop_oracle_entries removed FUNC entries"
    )
    assert "statement mismatch" in generate_prompt
