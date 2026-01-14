from __future__ import annotations

from c_rust.oracles.function_diff_test_oracle.trace_comparator import (
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
