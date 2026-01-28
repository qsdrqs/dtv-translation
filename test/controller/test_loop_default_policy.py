from __future__ import annotations

from dataclasses import dataclass

from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from core.budget import Budget
from core.llm_output import FenceState
from core.types import (
    Action,
    Artifact,
    GenerateContext,
    GenerateResult,
    Granularity,
    OracleOutput,
    RenderResult,
    RenderStatus,
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


class _SequenceGenerator:
    def __init__(self, steps: list[_Step]) -> None:
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
        step = self.steps[self.idx]
        self.idx += 1
        return GenerateResult(
            delta_text=step.text,
            delta_tokens=step.tokens,
            stop_reason=step.stop_reason,
        )

    def reset_output_extractor(self) -> None:
        return None

    def get_output_extractor_state(self) -> FenceState:
        return FenceState.OUTSIDE


class _OkRenderer:
    def try_render(self, prefix: str, granularity: Granularity) -> RenderResult:
        artifact = Artifact(code=prefix, granularity=granularity)
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


class _SequenceRenderer:
    def __init__(self, statuses: list[RenderStatus]) -> None:
        self.statuses = statuses
        self.calls = 0

    def try_render(self, prefix: str, granularity: Granularity) -> RenderResult:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        if status == RenderStatus.OK:
            artifact = Artifact(code=prefix, granularity=granularity)
            return RenderResult(status=status, artifact=artifact)
        return RenderResult(status=status, artifact=None, notes="mock")


class _SequenceOracle:
    def __init__(
        self,
        verdicts: list[Verdict],
        *,
        name: str = "oracle",
        required_granularity: Granularity = Granularity.STMT,
    ) -> None:
        self.verdicts = verdicts
        self.name = name
        self.required_granularity = required_granularity
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
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=(),
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
        max_steps=max_steps,
    )


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


def test_default_policy_retry_after_fail() -> None:
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


def test_default_policy_no_oracles_continue_then_generate() -> None:
    generator = _SequenceGenerator([
        _Step("let x = 1;", StopReason(kind="boundary")),
        _Step("let y = 2;", StopReason(kind="eos")),
    ])
    renderer = _OkRenderer()
    oracles = [_SequenceOracle([Verdict.PASS], required_granularity=Granularity.PROGRAM)]
    policy = DefaultPolicy(DefaultPolicyConfig(terminate_on_eos_and_pass=False))

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
    assert final_prefix == "let x = 1;let y = 2;"


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
        _Step("fn main() {}", StopReason(kind="eos")),
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
