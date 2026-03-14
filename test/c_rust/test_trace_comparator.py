from __future__ import annotations

from core.trace_comparator import (
    find_first_mismatch,
    parse_trace_events,
)
from core.types import ExecutionTraceEvent, TraceEventKind


def test_parse_trace_events_includes_args_ret_ptr_args() -> None:
    stderr = "\n".join(
        [
            '{"kind":"func_enter","id":"f","args":[{"ty":"i32","val":1}]}',
            "not json",
            '{"kind":"func_exit","id":"f","ret":{"ty":"i32","val":2},"ptr_args":[{"ty":"ptr_i32","val":3}]}',
        ]
    )
    events = parse_trace_events(stderr)

    assert [event.kind for event in events] == [TraceEventKind.FUNC_ENTER, TraceEventKind.FUNC_EXIT]
    assert events[0].args == [{"ty": "i32", "val": 1}]
    assert events[1].ret == {"ty": "i32", "val": 2}
    assert events[1].ptr_args == [{"ty": "ptr_i32", "val": 3}]


def test_find_first_mismatch_skips_placeholder_and_counts() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "unsupported", "skip": True, "reason": "struct"},
                {"ty": "i32", "val": 1},
            ],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "i32", "val": 999},
                {"ty": "i32", "val": 1},
            ],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is None
    assert stats.total_fields == 2
    assert stats.skipped_fields == 1
    assert stats.compared_fields == 1


def test_find_first_mismatch_detects_value_mismatch() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret={"ty": "i32", "val": 1},
            ptr_args=[],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret={"ty": "i32", "val": 2},
            ptr_args=[],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "ret mismatch" in mismatch.message
    assert stats.total_fields == 1
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 1


def test_find_first_mismatch_allows_ptr_len_vs_slice_arg_length() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
                {"ty": "usize", "val": 3},
            ],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
            ],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is None
    assert stats.total_fields == 2
    assert stats.skipped_fields == 1
    assert stats.compared_fields == 1


def test_find_first_mismatch_ptr_len_pointer_type_mismatch() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
                {"ty": "usize", "val": 3},
            ],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i64", "val": 1},
            ],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "pointer type mismatch" in mismatch.message
    assert stats.total_fields == 0
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 0


def test_find_first_mismatch_ptr_len_len_type_not_integer() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
                {"ty": "f32", "val": "0x00000003"},
            ],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
            ],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "args length mismatch" in mismatch.message
    assert stats.total_fields == 0
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 0


def test_find_first_mismatch_ptr_len_pointer_value_mismatch() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
                {"ty": "usize", "val": 3},
            ],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 2},
            ],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "args[0] mismatch" in mismatch.message
    assert stats.total_fields == 2
    assert stats.skipped_fields == 1
    assert stats.compared_fields == 1


def test_find_first_mismatch_args_len_mismatch_non_slice_pattern() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
            ],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_ENTER,
            id="f",
            args=[
                {"ty": "ptr_i32", "val": 1},
                {"ty": "usize", "val": 3},
            ],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "args length mismatch" in mismatch.message
    assert stats.total_fields == 0
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 0


def test_find_first_mismatch_detects_ptr_args_value_mismatch() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret={"ty": "i32", "val": 0},
            ptr_args=[{"ty": "ptr_i32", "val": 1}],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret={"ty": "i32", "val": 0},
            ptr_args=[{"ty": "ptr_i32", "val": 2}],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "ptr_args[0] mismatch" in mismatch.message
    assert stats.total_fields == 2
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 2


def test_find_first_mismatch_detects_ptr_args_presence_mismatch() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret=None,
            ptr_args=None,
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret=None,
            ptr_args=[],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "ptr_args presence mismatch" in mismatch.message
    assert stats.total_fields == 0
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 0


def test_find_first_mismatch_detects_ptr_args_length_mismatch() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret=None,
            ptr_args=[{"ty": "ptr_i32", "val": 1}],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret=None,
            ptr_args=[
                {"ty": "ptr_i32", "val": 1},
                {"ty": "ptr_i32", "val": 2},
            ],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "ptr_args length mismatch" in mismatch.message
    assert stats.total_fields == 0
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 0


def test_find_first_mismatch_skips_ptr_args_placeholder() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret=None,
            ptr_args=[{"ty": "ptr_i32", "val": 1}],
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret=None,
            ptr_args=[{"ty": "unsupported", "skip": True, "reason": "struct"}],
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is None
    assert stats.total_fields == 1
    assert stats.skipped_fields == 1
    assert stats.compared_fields == 0


def test_find_first_mismatch_detects_ret_presence_mismatch() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret=None,
            ptr_args=None,
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret={"ty": "i32", "val": 0},
            ptr_args=None,
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is not None
    assert "ret presence mismatch" in mismatch.message
    assert stats.total_fields == 0
    assert stats.skipped_fields == 0
    assert stats.compared_fields == 0


def test_find_first_mismatch_skips_ret_placeholder() -> None:
    c_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret={"ty": "unsupported", "skip": True, "reason": "struct"},
            ptr_args=None,
        )
    ]
    rust_trace = [
        ExecutionTraceEvent(
            kind=TraceEventKind.FUNC_EXIT,
            id="f",
            ret={"ty": "i32", "val": 1},
            ptr_args=None,
        )
    ]

    mismatch, stats = find_first_mismatch(c_trace, rust_trace)

    assert mismatch is None
    assert stats.total_fields == 1
    assert stats.skipped_fields == 1
    assert stats.compared_fields == 0
