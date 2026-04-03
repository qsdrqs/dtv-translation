from __future__ import annotations

from core.llm_output import AssistantContent, FenceState
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
        fence_lang="typescript",
        code="- old\n+ ",
        fence_state=FenceState.INSIDE,
    )

    assert _render_feedback_patch_text(prefix, "new\n") == """```typescript
- old
+ new
"""
