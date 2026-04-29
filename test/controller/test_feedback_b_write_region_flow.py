from __future__ import annotations

from dataclasses import dataclass

from c_rust.feedback import RUST_FEEDBACK_LANG
from controller.loop import ControllerOp, _render_feedback_patch_text, run_dtv_loop
from core.budget import Budget
from core.llm_output import AssistantContent, OutputExtractorState, WriteRegionMarkers, WriteRegionParserSnapshot, WriteRegionState
from core.types import (
    Action,
    Artifact,
    Diagnostic,
    FeedbackMechanism,
    GenerateContext,
    GenerateMessage,
    GenerateResult,
    GenerationChannel,
    Granularity,
    OracleOutput,
    RenderResult,
    RenderStatus,
    StopReason,
    Verdict,
)
from feedback.feedback import FeedbackState
from feedback.output_parser import parse_diff_feedback_output
from rollback.manager import RollbackManager


BROKEN_STMT = 'let x: i32 = "1";\n'
PHASE1_REASONING = "I should replace the string literal with an integer.\n"


@dataclass(frozen=True)
class RecordedCall:
    index: int
    channel: GenerationChannel
    extract_write_region: bool
    stop_on_write_region_open: bool
    messages: tuple[GenerateMessage, ...]
    result: GenerateResult


class _ScriptedFeedbackBGenerator:
    def __init__(self, markers: WriteRegionMarkers) -> None:
        self._markers = markers
        self._call_index = 0
        self._calls: list[RecordedCall] = []
        self._stop_on_write_region_open = False
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    @property
    def calls(self) -> list[RecordedCall]:
        return list(self._calls)

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        result = self._next_result()
        self._calls.append(
            RecordedCall(
                index=self._call_index,
                channel=context.channel,
                extract_write_region=context.extract_write_region,
                stop_on_write_region_open=self._stop_on_write_region_open,
                messages=tuple(_clone_message(msg) for msg in context.messages),
                result=result,
            )
        )
        self._call_index += 1
        return result

    def reset_output_extractor(self) -> None:
        snapshot = WriteRegionParserSnapshot(state=WriteRegionState.OUTSIDE, saw_begin=False, saw_end=False)
        self._extractor_state = OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def get_output_extractor_state(self) -> WriteRegionState:
        return self._extractor_state.extract.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        return self._extractor_state

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._extractor_state = state

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        self._stop_on_write_region_open = enabled

    def _next_result(self) -> GenerateResult:
        if self._call_index == 0:
            inside = WriteRegionParserSnapshot(
                state=WriteRegionState.INSIDE,
                saw_begin=True,
                saw_end=False,
            )
            self._extractor_state = OutputExtractorState(
                segment=inside,
                extract=inside,
                shared=inside,
                warning_emitted=False,
            )
            return GenerateResult(
                delta_text=BROKEN_STMT,
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
                assistant_delta=AssistantContent(
                    prelude="Here is the in-progress candidate.\n",
                    code=BROKEN_STMT,
                    has_begin_marker=True,
                    region_state=WriteRegionState.INSIDE,
                    markers=self._markers,
                ),
            )
        if self._call_index == 1:
            return GenerateResult(
                delta_text="",
                delta_tokens=2,
                stop_reason=StopReason(kind="unknown"),
                assistant_delta=AssistantContent(
                    prelude=PHASE1_REASONING,
                    code="",
                    has_begin_marker=True,
                    region_state=WriteRegionState.INSIDE,
                    markers=self._markers,
                ),
            )
        if self._call_index == 2:
            return GenerateResult(
                delta_text=f"let x: i32 = 1;\n{self._markers.end_marker}\n",
                delta_tokens=3,
                stop_reason=StopReason(kind="unknown"),
            )
        return GenerateResult(delta_text="", delta_tokens=0, stop_reason=StopReason(kind="empty"))


class _FailingStmtOracle:
    name = "rustc"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        _ = context
        return OracleOutput(
            oracle_name=self.name,
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(
                    message='expected `i32`, found `&str`',
                    severity="error",
                    error_code="E0308",
                ),
            ),
            rendered_diagnostics=("- rendered: expected `i32`, found `&str` (E0308)",),
            rollback_scope=Granularity.STMT,
        )


class _OkRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        return RenderResult(status=RenderStatus.OK, artifact=Artifact(code=prefix))


class _FeedbackBApplyPatchPolicy:
    def __init__(self) -> None:
        self._stage = 0

    def next_action(self, ctx) -> ControllerOp:
        _ = ctx
        if self._stage == 0:
            self._stage = 1
            return ControllerOp(Action.GENERATE)
        if self._stage == 1:
            self._stage = 2
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if self._stage == 2:
            self._stage = 3
            return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
        if self._stage == 3:
            self._stage = 4
            return ControllerOp(Action.FEEDBACK, feedback_mechanism=FeedbackMechanism.B)
        if self._stage == 4:
            self._stage = 5
            return ControllerOp(Action.APPLY_PATCH)
        return ControllerOp(Action.TERMINATE)

    def reset_round_state(self) -> None:
        pass

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        _ = artifact
        _ = budget
        _ = selection_granularity
        return list(available)


def _clone_message(msg: GenerateMessage | dict[str, object]) -> GenerateMessage:
    if isinstance(msg, dict):
        return GenerateMessage(
            role=str(msg.get("role", "")),
            content=str(msg.get("content", "")),
            stop=bool(msg.get("stop", False)),
        )
    content = msg.content
    if isinstance(content, AssistantContent):
        content = AssistantContent(
            prelude=content.prelude,
            code=content.code,
            postlude=content.postlude,
            pending_text=content.pending_text,
            has_begin_marker=content.has_begin_marker,
            has_end_marker=content.has_end_marker,
            region_state=content.region_state,
            markers=content.markers,
        )
    return GenerateMessage(role=msg.role, content=content, stop=msg.stop)


def _last_user_message(call: RecordedCall) -> str:
    for msg in reversed(call.messages):
        if msg.role == "user":
            return _render_message_content(msg)
    return ""


def _last_assistant_message(call: RecordedCall) -> str:
    for msg in reversed(call.messages):
        if msg.role == "assistant":
            return _render_message_content(msg)
    return ""


def _last_assistant_content(call: RecordedCall) -> str | AssistantContent | None:
    for msg in reversed(call.messages):
        if msg.role == "assistant":
            return msg.content
    return None


def _render_message_content(msg: GenerateMessage) -> str:
    if isinstance(msg.content, AssistantContent):
        return msg.content.render()
    return str(msg.content)


def test_feedback_b_end_to_end_default_markers() -> None:
    markers = WriteRegionMarkers()
    generator = _ScriptedFeedbackBGenerator(markers)

    output, trace = run_dtv_loop(
        generator=generator,
        renderer=_OkRenderer(),
        oracles=[_FailingStmtOracle()],
        budget=Budget(gen_tokens_budget=32),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(markers=markers),
        policy=_FeedbackBApplyPatchPolicy(),
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=8,
        prompt_prefix="Translate the program to Rust.",
        write_region_markers=markers,
    )

    assert "let x: i32 = 1;" in output
    assert [event.action for event in trace] == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.TERMINATE,
    ]

    generate_call, phase1_call, phase2_call = generator.calls[:3]
    assert generate_call.channel == GenerationChannel.CONTINUATION
    assert phase1_call.channel == GenerationChannel.CONTINUATION
    assert phase1_call.stop_on_write_region_open is True
    assert phase2_call.channel == GenerationChannel.PATCH

    assert markers.begin_marker in _last_user_message(generate_call)
    assert "Return exactly one write-code region containing the unified diff patch:" in _last_user_message(phase1_call)

    phase2_prefix = _last_assistant_content(phase2_call)
    assert isinstance(phase2_prefix, AssistantContent)
    assert _last_assistant_message(phase2_call) == (
        f"{PHASE1_REASONING}"
        f"{markers.begin_marker}\n"
        "- let x: i32 = \"1\";\n"
        "+ "
    )

    patch_text = _render_feedback_patch_text(phase2_prefix, phase2_call.result.delta_text)
    parse_result = parse_diff_feedback_output(patch_text, markers=markers)
    assert patch_text == (
        f"{markers.begin_marker}\n"
        "- let x: i32 = \"1\";\n"
        "+ let x: i32 = 1;\n"
        f"{markers.end_marker}\n"
    )
    assert parse_result.error is None
    assert parse_result.patch == "let x: i32 = 1;"


def test_feedback_b_end_to_end_custom_markers() -> None:
    markers = WriteRegionMarkers(begin_marker="[[BEGIN]]", end_marker="[[END]]")
    generator = _ScriptedFeedbackBGenerator(markers)

    output, trace = run_dtv_loop(
        generator=generator,
        renderer=_OkRenderer(),
        oracles=[_FailingStmtOracle()],
        budget=Budget(gen_tokens_budget=32),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(markers=markers),
        policy=_FeedbackBApplyPatchPolicy(),
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=8,
        write_region_markers=markers,
    )

    assert "let x: i32 = 1;" in output
    assert [event.action for event in trace][-2:] == [Action.APPLY_PATCH, Action.TERMINATE]

    _, phase1_call, phase2_call = generator.calls[:3]
    assert "[[BEGIN]]" in _last_user_message(phase1_call)
    assert "[[END]]" in _last_user_message(phase1_call)

    phase2_prefix = _last_assistant_content(phase2_call)
    assert isinstance(phase2_prefix, AssistantContent)
    patch_text = _render_feedback_patch_text(phase2_prefix, phase2_call.result.delta_text)
    parse_result = parse_diff_feedback_output(patch_text, markers=markers)
    assert patch_text.startswith("[[BEGIN]]\n")
    assert patch_text.endswith("[[END]]\n")
    assert parse_result.error is None
    assert parse_result.patch == "let x: i32 = 1;"
