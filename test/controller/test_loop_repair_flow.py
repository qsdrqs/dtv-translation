from __future__ import annotations

import pytest

from controller.loop import ControllerOp, run_dtv_loop, select_oracles_by_granularity
from core.budget import Budget
from core.llm_output import FenceParserSnapshot, FenceState, OutputExtractorState
from core.types import (
    Action,
    Artifact,
    FeedbackMechanism,
    GenerateContext,
    GenerateResult,
    Granularity,
    RenderResult,
    RenderStatus,
    RollbackScope,
    StopReason,
    Verdict,
)
from feedback.formatter import RepairFeedbackFormatConfig
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


class _OracleFail:
    name = "oracle"
    required_granularity = Granularity.STMT
    rollback_scope = RollbackScope.STMT

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
    rollback_scope = RollbackScope.STMT

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
            return ControllerOp(Action.ROLLBACK, rollback_scope=RollbackScope.STMT)
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
            return ControllerOp(Action.ROLLBACK, rollback_scope=RollbackScope.STMT)
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


def test_continue_then_generate_raises_when_feedback_payload_exists() -> None:
    generator = _SequenceGenerator(["bad stmt\n", "fix\n"])
    renderer = _OkRenderer()
    oracles = [_OracleFail()]
    budget = Budget(gen_tokens_budget=8)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = _ContinueGeneratePolicy()

    with pytest.raises(RuntimeError, match="Action.GENERATE cannot include feedback payload"):
        run_dtv_loop(
            generator=generator,
            renderer=renderer,
            oracles=oracles,
            budget=budget,
            feedback_state=feedback_state,
            rollback_manager=rollback_manager,
            policy=policy,
            max_steps=7,
        )


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
        repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=False),
        max_steps=6,
    )

    assert any(event.action == Action.FEEDBACK for event in trace)
    assert generator.seen_user_messages
    feedback_prompt = generator.seen_user_messages[-1]
    assert "diagnostics:" in feedback_prompt
    assert "failed snippet:" not in feedback_prompt


def test_structured_feedback_mechanism_b_applies_parsed_patch() -> None:
    generator = _SequenceGenerator(["bad stmt\n", "```rust\ngood;\n```"])
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


def test_structured_feedback_mechanism_b_parser_failure_feeds_next_round() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            """```rust
first;
```
```rust
second;
```""",
            "```rust\nfixed;\n```",
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
        max_steps=7,
    )

    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 2
    assert all(event.notes == "feedback_mechanism=b" for event in feedback_events)
    assert generator.seen_user_messages[-1].count("Previous parse error:") == 1
    assert "multiple fenced code blocks found" in generator.seen_user_messages[-1]


def test_structured_feedback_mechanism_b_scope_validator_failure_feeds_next_round() -> None:
    generator = _TrackingSequenceGenerator(
        [
            "bad stmt\n",
            """```rust
fn main() {
    let x: i32 = 1;
}
```""",
            "```rust\nfixed;\n```",
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
        max_steps=7,
    )

    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 2
    assert all(event.notes == "feedback_mechanism=b" for event in feedback_events)
    assert Action.APPLY_PATCH not in [event.action for event in trace]
    assert generator.seen_user_messages[-1].count("Previous parse error:") == 1
    assert "stmt-scope patch cannot include top-level items (function_item)" in generator.seen_user_messages[-1]
