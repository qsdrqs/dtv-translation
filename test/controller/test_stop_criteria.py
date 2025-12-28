from __future__ import annotations

from controller.stop_criteria import (
    RUST_PROFILE,
    TS_PROFILE,
    _scan_string_comment_state,
)


def test_empty() -> None:
    state = _scan_string_comment_state("", TS_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_line_comment_unterminated() -> None:
    state = _scan_string_comment_state("let x = 1; // comment", TS_PROFILE)
    assert state["in_line_comment"]
    assert not state["in_string"]
    assert not state["in_block_comment"]


def test_line_comment_terminated_by_newline() -> None:
    state = _scan_string_comment_state("let x = 1; // comment\nlet y = 2;", TS_PROFILE)
    assert not state["in_line_comment"]
    assert not state["in_string"]
    assert not state["in_block_comment"]


def test_block_comment_unterminated() -> None:
    state = _scan_string_comment_state("let x = 1; /* comment", TS_PROFILE)
    assert state["in_block_comment"]
    assert not state["in_string"]
    assert not state["in_line_comment"]


def test_block_comment_terminated() -> None:
    state = _scan_string_comment_state("let x = 1; /* comment */ let y = 2;", TS_PROFILE)
    assert not state["in_block_comment"]
    assert not state["in_string"]
    assert not state["in_line_comment"]


def test_comment_markers_inside_string_not_counted() -> None:
    state = _scan_string_comment_state('let s = "// not a comment";', TS_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_escaped_quote_inside_string() -> None:
    state = _scan_string_comment_state('let s = "a \\" b";', TS_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_ts_backtick_string() -> None:
    state = _scan_string_comment_state("const s = `hello", TS_PROFILE)
    assert state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_rust_does_not_treat_backticks_as_string() -> None:
    state = _scan_string_comment_state("let s = `hello", RUST_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]
