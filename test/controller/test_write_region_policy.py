from __future__ import annotations

from c_rust.feedback import RUST_FEEDBACK_LANG
from controller.loop import ControllerOp, PolicyContext, _render_feedback_patch_text, run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from core.budget import Budget
from core.llm_output import AssistantContent, BEGIN_WRITE_CODE, END_WRITE_CODE, OutputExtractorState, WriteRegionMarkers, WriteRegionParserSnapshot, WriteRegionState
from core.types import Action, Artifact, ControllerState, GenerateContext, GenerateMessage, GenerateResult, Granularity, OracleOutput, RenderResult, RenderStatus, StopReason, Verdict
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


def _ctx(*, last_action: Action | None, last_stop_reason: StopReason | None, prefix: str = "", last_render_status: RenderStatus | None = None, last_outputs=(), last_artifact: Artifact | None = None) -> PolicyContext:
    return PolicyContext(
        state=ControllerState(prefix=prefix),
        budget=Budget(gen_tokens_budget=8),
        rollback=RollbackManager(),
        last_action=last_action,
        last_stop_reason=last_stop_reason,
        last_render_status=last_render_status,
        last_artifact=last_artifact,
        last_outputs=last_outputs,
        failed_prefix=None,
        pending_patch=None,
        repair_base_prefix=None,
        repair_scope=None,
        write_region_state=WriteRegionState.OUTSIDE,
    )


def test_default_policy_closed_candidate_verifies_then_terminates() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(commit_when_no_oracle_selected=True))

    op = policy.next_action(_ctx(
        last_action=Action.GENERATE,
        last_stop_reason=StopReason(kind="write_region_closed"),
        prefix="let x = 1;",
    ))
    assert op.action == Action.VERIFY

    op = policy.next_action(_ctx(
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="write_region_closed"),
        prefix="let x = 1;",
        last_render_status=RenderStatus.OK,
        last_outputs=(),
        last_artifact=Artifact(code="let x = 1;"),
    ))
    assert op.action == Action.COMMIT

    op = policy.next_action(_ctx(
        last_action=Action.COMMIT,
        last_stop_reason=StopReason(kind="write_region_closed"),
        prefix="let x = 1;",
    ))
    assert op.action == Action.TERMINATE


def test_default_policy_caps_program_fail_scope_to_func() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig())

    op = policy.next_action(_ctx(
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="boundary"),
        prefix="fn f() { bad(); }",
        last_render_status=RenderStatus.OK,
        last_artifact=Artifact(code="fn f() { bad(); }"),
        last_outputs=(
            OracleOutput(
                oracle_name="external-program-like",
                verdict=Verdict.FAIL,
                rollback_scope=Granularity.PROGRAM,
            ),
        ),
    ))

    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == Granularity.FUNC


class _ClosedCandidateGenerator:
    def __init__(self) -> None:
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )
        self._generated = False

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        _ = context
        if self._generated:
            return GenerateResult(delta_text="", delta_tokens=0, stop_reason=StopReason(kind="empty"))
        self._generated = True
        closed = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=True, saw_end=True)
        self._extractor_state = OutputExtractorState(
            segment=closed,
            extract=closed,
            shared=closed,
            warning_emitted=False,
        )
        return GenerateResult(
            delta_text="let x = 1;",
            delta_tokens=1,
            stop_reason=StopReason(kind="write_region_closed"),
            assistant_delta=AssistantContent(
                prelude="Reasoning\n",
                code="let x = 1;",
                has_begin_marker=True,
                has_end_marker=True,
                region_state=WriteRegionState.OUTSIDE,
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


class _OkRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        return RenderResult(status=RenderStatus.OK, artifact=Artifact(code=prefix))


def test_run_dtv_loop_returns_single_closed_candidate() -> None:
    output, trace = run_dtv_loop(
        generator=_ClosedCandidateGenerator(),
        renderer=_OkRenderer(),
        oracles=[],
        budget=Budget(gen_tokens_budget=8),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(),
        policy=DefaultPolicy(DefaultPolicyConfig(commit_when_no_oracle_selected=True)),
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=4,
    )

    assert output == "let x = 1;"
    assert [event.action for event in trace] == [
        Action.GENERATE,
        Action.VERIFY,
        Action.COMMIT,
        Action.TERMINATE,
    ]


def test_render_feedback_patch_text_drops_reasoning_prelude() -> None:
    prefix = AssistantContent(
        prelude="reasoning\n",
        code="+ fixed();\n",
        has_begin_marker=True,
        region_state=WriteRegionState.INSIDE,
    )

    rendered = _render_feedback_patch_text(prefix, f"{END_WRITE_CODE}\n")

    assert rendered.startswith(f"{BEGIN_WRITE_CODE}\n")
    assert "reasoning" not in rendered


class _PromptCapturingGenerator(_ClosedCandidateGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.seen_messages = None

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        self.seen_messages = context.messages
        return super().generate_step(context)


def test_run_dtv_loop_injects_write_region_contract_into_initial_prompt() -> None:
    generator = _PromptCapturingGenerator()

    run_dtv_loop(
        generator=generator,
        renderer=_OkRenderer(),
        oracles=[],
        budget=Budget(gen_tokens_budget=8),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(),
        policy=DefaultPolicy(DefaultPolicyConfig(commit_when_no_oracle_selected=True)),
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=4,
        prompt_prefix="Translate this program.",
    )

    assert generator.seen_messages is not None
    first = generator.seen_messages[0]
    assert isinstance(first, GenerateMessage)
    assert isinstance(first.content, str)
    assert BEGIN_WRITE_CODE in first.content
    assert END_WRITE_CODE in first.content


def test_run_dtv_loop_uses_custom_markers_in_initial_prompt() -> None:
    markers = WriteRegionMarkers(begin_marker="[[BEGIN]]", end_marker="[[END]]")
    generator = _PromptCapturingGenerator()

    run_dtv_loop(
        generator=generator,
        renderer=_OkRenderer(),
        oracles=[],
        budget=Budget(gen_tokens_budget=8),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(),
        policy=DefaultPolicy(DefaultPolicyConfig(commit_when_no_oracle_selected=True)),
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=4,
        write_region_markers=markers,
    )

    assert generator.seen_messages is not None
    first = generator.seen_messages[0]
    assert isinstance(first, GenerateMessage)
    assert isinstance(first.content, str)
    assert "[[BEGIN]]" in first.content
    assert "[[END]]" in first.content
