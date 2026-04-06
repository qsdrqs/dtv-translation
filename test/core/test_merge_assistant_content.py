from __future__ import annotations

from core.llm_output import AssistantContent, WriteRegionState, merge_assistant_content


def test_merge_empty() -> None:
    merged = merge_assistant_content(AssistantContent.empty(), AssistantContent.empty())
    assert merged == AssistantContent.empty()
    assert merged.region_state == WriteRegionState.OUTSIDE


def test_merge_prelude_concat() -> None:
    prefix = AssistantContent(prelude="a")
    delta = AssistantContent(prelude="b")
    merged = merge_assistant_content(prefix, delta)
    assert merged.prelude == "ab"


def test_merge_code_concat() -> None:
    prefix = AssistantContent(code="line1\n", has_begin_marker=True, region_state=WriteRegionState.INSIDE)
    delta = AssistantContent(code="line2\n", has_begin_marker=True, region_state=WriteRegionState.INSIDE)
    merged = merge_assistant_content(prefix, delta)
    assert merged.code == "line1\nline2\n"


def test_merge_postlude_and_markers() -> None:
    prefix = AssistantContent(has_begin_marker=True, code="x\n", region_state=WriteRegionState.INSIDE)
    delta = AssistantContent(postlude="done\n", has_end_marker=True, region_state=WriteRegionState.OUTSIDE)
    merged = merge_assistant_content(prefix, delta)
    assert merged.has_begin_marker
    assert merged.has_end_marker
    assert merged.postlude == "done\n"
    assert merged.region_state == WriteRegionState.OUTSIDE


def test_merge_pending_text_overwrites() -> None:
    prefix = AssistantContent(pending_text="<<END")
    delta = AssistantContent(pending_text="")
    merged = merge_assistant_content(prefix, delta)
    assert merged.pending_text == ""
