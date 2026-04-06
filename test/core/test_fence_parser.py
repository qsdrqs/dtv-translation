from __future__ import annotations

from core.llm_output import BEGIN_WRITE_CODE, END_WRITE_CODE, WriteRegionMarkers, WriteRegionParser, WriteRegionState


def test_parser_tracks_write_region_and_output() -> None:
    parser = WriteRegionParser()

    delta = parser.feed("preamble\n")
    assert parser.state == WriteRegionState.OUTSIDE
    assert delta.prelude == "preamble\n"
    assert parser.consume_code() == ""

    delta = parser.feed(f"{BEGIN_WRITE_CODE}\n")
    assert parser.state == WriteRegionState.INSIDE
    assert delta.has_begin_marker

    delta = parser.feed("let x = 1;\n")
    assert delta.code == "let x = 1;\n"
    assert parser.consume_code() == "let x = 1;\n"

    delta = parser.feed(f"{END_WRITE_CODE}\n")
    assert parser.state == WriteRegionState.OUTSIDE
    assert delta.has_end_marker

    delta = parser.feed("after\n")
    assert delta.postlude == "after\n"


def test_parser_buffers_split_begin_marker() -> None:
    parser = WriteRegionParser()

    delta = parser.feed("<<BEGIN_")
    assert delta.pending_text == "<<BEGIN_"
    assert parser.state == WriteRegionState.OUTSIDE

    delta = parser.feed("WRITE_CODE>>\ncode")
    assert delta.has_begin_marker
    assert delta.code == "code"
    assert parser.consume_code() == "code"


def test_parser_rejects_inner_fence() -> None:
    parser = WriteRegionParser()

    parser.feed(f"{BEGIN_WRITE_CODE}\n")
    parser.feed("```rust\n")

    assert parser.invalid_payload
    assert parser.invalid_reason == "write region must contain raw code only"


def test_feed_empty_preserves_state() -> None:
    parser = WriteRegionParser()
    parser.feed(f"{BEGIN_WRITE_CODE}\n")

    delta = parser.feed("")

    assert parser.state == WriteRegionState.INSIDE
    assert delta.region_state == WriteRegionState.INSIDE


def test_parser_accepts_custom_markers() -> None:
    markers = WriteRegionMarkers(begin_marker="[[BEGIN]]", end_marker="[[END]]")
    parser = WriteRegionParser(markers=markers)

    delta = parser.feed("[[BEGIN]]\nanswer\n[[END]]\n")

    assert delta.has_begin_marker
    assert delta.has_end_marker
    assert delta.markers == markers
    assert parser.consume_code() == "answer\n"
