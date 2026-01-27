from __future__ import annotations

from core.llm_output import AssistantContent, FenceState, merge_assistant_content


def test_merge_empty() -> None:
    merged = merge_assistant_content(AssistantContent.empty(), AssistantContent.empty())
    assert merged == AssistantContent.empty()
    assert merged.fence_state == FenceState.OUTSIDE


def test_merge_pre_fence_concat() -> None:
    prefix = AssistantContent(pre_fence="a")
    delta = AssistantContent(pre_fence="b")
    merged = merge_assistant_content(prefix, delta)
    assert merged.pre_fence == "ab"


def test_merge_fence_lang_prefers_prefix() -> None:
    prefix = AssistantContent(fence_lang="rust")
    delta = AssistantContent(fence_lang="rs")
    merged = merge_assistant_content(prefix, delta)
    assert merged.fence_lang == "rust"


def test_merge_code_concat() -> None:
    prefix = AssistantContent(code="line1\n")
    delta = AssistantContent(code="line2\n")
    merged = merge_assistant_content(prefix, delta)
    assert merged.code == "line1\nline2\n"


def test_merge_post_fence_and_state_from_delta() -> None:
    prefix = AssistantContent(post_fence="p1", fence_state=FenceState.INSIDE)
    delta = AssistantContent(post_fence="p2", fence_state=FenceState.DONE)
    merged = merge_assistant_content(prefix, delta)
    assert merged.post_fence == "p1p2"
    assert merged.fence_state == FenceState.DONE


def test_merge_pending_text_overwrites() -> None:
    prefix = AssistantContent(pending_text="``")
    delta = AssistantContent(pending_text="")
    merged = merge_assistant_content(prefix, delta)
    assert merged.pending_text == ""
