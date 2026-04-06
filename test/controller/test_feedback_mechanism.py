from __future__ import annotations

from core.llm_output import AssistantContent, BEGIN_WRITE_CODE, WriteRegionState
from core.types import FeedbackMechanism, Granularity
from controller.loop import _render_feedback_patch_text, _select_feedback_mechanism


def test_select_feedback_mechanism_keeps_b_for_stmt_scope() -> None:
    assert _select_feedback_mechanism(
        requested_mechanism=FeedbackMechanism.B,
        repair_scope=Granularity.STMT,
    ) == FeedbackMechanism.B


def test_select_feedback_mechanism_downgrades_b_for_non_stmt_scope() -> None:
    assert _select_feedback_mechanism(
        requested_mechanism=FeedbackMechanism.B,
        repair_scope=Granularity.FUNC,
    ) == FeedbackMechanism.A
    assert _select_feedback_mechanism(
        requested_mechanism=FeedbackMechanism.B,
        repair_scope=Granularity.BLOCK,
    ) == FeedbackMechanism.A
    assert _select_feedback_mechanism(
        requested_mechanism=FeedbackMechanism.B,
        repair_scope=Granularity.PROGRAM,
    ) == FeedbackMechanism.A


def test_select_feedback_mechanism_keeps_a_for_any_scope() -> None:
    assert _select_feedback_mechanism(
        requested_mechanism=FeedbackMechanism.A,
        repair_scope=Granularity.STMT,
    ) == FeedbackMechanism.A
    assert _select_feedback_mechanism(
        requested_mechanism=FeedbackMechanism.A,
        repair_scope=Granularity.FUNC,
    ) == FeedbackMechanism.A


def test_render_feedback_patch_text_includes_prefill_content() -> None:
    prefix = AssistantContent(
        code="- old\n+ ",
        has_begin_marker=True,
        region_state=WriteRegionState.INSIDE,
    )

    assert _render_feedback_patch_text(prefix, "new\n") == f"""{BEGIN_WRITE_CODE}
- old
+ new
"""
