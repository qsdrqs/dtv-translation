"""Language-agnostic trace comparison utilities for differential testing oracles."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from core.types import ExecutionTraceEvent, Mismatch, Granularity, TraceEventKind


def parse_trace_events(stderr: str) -> list[ExecutionTraceEvent]:
    """Parse JSON trace events from stderr, ignoring non-JSON lines."""
    events = []
    for line in stderr.strip().split('\n'):
        if not line:
            continue
        try:
            data = json.loads(line)
            kind_str = data.get('kind')
            if kind_str not in ('func_enter', 'func_exit', 'block_enter', 'block_exit'):
                continue  # Skip non-trace JSON (e.g., other log messages)

            event = ExecutionTraceEvent(
                kind=TraceEventKind(kind_str),
                id=data['id'],
                timestamp_us=data.get('timestamp'),
                depth=data.get('depth'),
                args=data.get('args'),
                ret=data.get('ret'),
                ptr_args=data.get('ptr_args'),
            )
            events.append(event)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue  # Skip invalid JSON, compiler warnings, debug output

    return events


@dataclass
class TraceComparisonStats:
    total_fields: int = 0
    compared_fields: int = 0
    skipped_fields: int = 0

    def add(self, other: "TraceComparisonStats") -> None:
        self.total_fields += other.total_fields
        self.compared_fields += other.compared_fields
        self.skipped_fields += other.skipped_fields


def find_first_mismatch(
    c_trace: list[ExecutionTraceEvent],
    rust_trace: list[ExecutionTraceEvent],
    scope: Granularity = Granularity.FUNC,
) -> tuple[Mismatch | None, TraceComparisonStats]:
    """Find first mismatch using longest common prefix."""
    stats = TraceComparisonStats()
    if len(c_trace) != len(rust_trace):
        shorter_len = min(len(c_trace), len(rust_trace))
        return Mismatch(
            position=shorter_len,
            c_value=f"trace_length={len(c_trace)}",
            rust_value=f"trace_length={len(rust_trace)}",
            message=f"Trace length mismatch at position {shorter_len} (C={len(c_trace)}, Rust={len(rust_trace)})",
            suggested_scope=scope,
        ), stats

    for i, (c_event, rust_event) in enumerate(zip(c_trace, rust_trace)):
        if not _events_match(c_event, rust_event):
            return Mismatch(
                position=i,
                c_value=_event_repr(c_event),
                rust_value=_event_repr(rust_event),
                message=f"Trace mismatch at position {i}: {_event_repr(c_event)} vs {_event_repr(rust_event)}",
                suggested_scope=scope,
            ), stats
        payload_mismatch = _compare_event_payload(c_event, rust_event, stats, i, scope)
        if payload_mismatch:
            return payload_mismatch, stats

    return None, stats


def filter_trace_for_function(
    events: list[ExecutionTraceEvent],
    function_name: str,
) -> list[ExecutionTraceEvent]:
    """Filter trace events to only func_enter/func_exit for a specific function."""
    return [
        event
        for event in events
        if event.kind in (TraceEventKind.FUNC_ENTER, TraceEventKind.FUNC_EXIT)
        and event.id == function_name
    ]


def remap_trace_function_id(
    events: list[ExecutionTraceEvent],
    function_name: str,
) -> list[ExecutionTraceEvent]:
    """Remap all event ids to a given function name (for cross-language name normalization)."""
    return [replace(event, id=function_name) for event in events]


def _events_match(c_event: ExecutionTraceEvent, rust_event: ExecutionTraceEvent) -> bool:
    return c_event.kind == rust_event.kind and c_event.id == rust_event.id


def _event_repr(event: ExecutionTraceEvent) -> str:
    return f"{event.kind.value}({event.id})"


def _compare_event_payload(
    c_event: ExecutionTraceEvent,
    rust_event: ExecutionTraceEvent,
    stats: TraceComparisonStats,
    position: int,
    scope: Granularity,
) -> Mismatch | None:
    if c_event.kind == TraceEventKind.FUNC_ENTER:
        return _compare_field_list(
            c_event.args,
            rust_event.args,
            stats,
            position,
            scope,
            field_name="args",
        )
    if c_event.kind == TraceEventKind.FUNC_EXIT:
        mismatch = _compare_field_object(
            c_event.ret,
            rust_event.ret,
            stats,
            position,
            scope,
            field_name="ret",
        )
        if mismatch:
            return mismatch
        return _compare_field_list(
            c_event.ptr_args,
            rust_event.ptr_args,
            stats,
            position,
            scope,
            field_name="ptr_args",
        )
    return None


def _compare_field_list(
    c_list: list[dict[str, Any]] | None,
    rust_list: list[dict[str, Any]] | None,
    stats: TraceComparisonStats,
    position: int,
    scope: Granularity,
    field_name: str,
) -> Mismatch | None:
    if c_list is None and rust_list is None:
        return None
    if c_list is None or rust_list is None:
        return Mismatch(
            position=position,
            c_value=f"{field_name}={'missing' if c_list is None else 'present'}",
            rust_value=f"{field_name}={'missing' if rust_list is None else 'present'}",
            message=f"{field_name} presence mismatch at position {position}",
            suggested_scope=scope,
        )
    if len(c_list) != len(rust_list):
        if field_name == "args":
            mismatch = _compare_slice_arg_lengths(
                c_list,
                rust_list,
                stats,
                position,
                scope,
            )
            if mismatch is None:
                return None
            return mismatch
        return Mismatch(
            position=position,
            c_value=f"{field_name}_len={len(c_list)}",
            rust_value=f"{field_name}_len={len(rust_list)}",
            message=f"{field_name} length mismatch at position {position} (C={len(c_list)}, Rust={len(rust_list)})",
            suggested_scope=scope,
        )
    for idx, (c_item, r_item) in enumerate(zip(c_list, rust_list)):
        mismatch = _compare_field_item(
            c_item,
            r_item,
            stats,
            position,
            scope,
            field_name=f"{field_name}[{idx}]",
        )
        if mismatch:
            return mismatch
    return None


def _compare_slice_arg_lengths(
    c_list: list[dict[str, Any]],
    rust_list: list[dict[str, Any]],
    stats: TraceComparisonStats,
    position: int,
    scope: Granularity,
) -> Mismatch | None:
    if len(c_list) == 2 and len(rust_list) == 1:
        c_ptr, c_len = c_list
        r_ptr = rust_list[0]
        if _is_ptr_arg(c_ptr) and _is_len_arg(c_len) and _is_ptr_arg(r_ptr):
            if c_ptr.get("ty") != r_ptr.get("ty"):
                return Mismatch(
                    position=position,
                    c_value=_item_repr(c_ptr),
                    rust_value=_item_repr(r_ptr),
                    message=(
                        "args[0] pointer type mismatch at position "
                        f"{position}: {_item_repr(c_ptr)} vs {_item_repr(r_ptr)}"
                    ),
                    suggested_scope=scope,
                )
            stats.total_fields += 1
            stats.skipped_fields += 1
            return _compare_field_item(c_ptr, r_ptr, stats, position, scope, field_name="args[0]")
    return Mismatch(
        position=position,
        c_value=f"args_len={len(c_list)}",
        rust_value=f"args_len={len(rust_list)}",
        message=f"args length mismatch at position {position} (C={len(c_list)}, Rust={len(rust_list)})",
        suggested_scope=scope,
    )


def _compare_field_object(
    c_obj: dict[str, Any] | None,
    rust_obj: dict[str, Any] | None,
    stats: TraceComparisonStats,
    position: int,
    scope: Granularity,
    field_name: str,
) -> Mismatch | None:
    if c_obj is None and rust_obj is None:
        return None
    if c_obj is None or rust_obj is None:
        return Mismatch(
            position=position,
            c_value=f"{field_name}={'missing' if c_obj is None else 'present'}",
            rust_value=f"{field_name}={'missing' if rust_obj is None else 'present'}",
            message=f"{field_name} presence mismatch at position {position}",
            suggested_scope=scope,
        )
    return _compare_field_item(c_obj, rust_obj, stats, position, scope, field_name)


def _compare_field_item(
    c_item: dict[str, Any],
    rust_item: dict[str, Any],
    stats: TraceComparisonStats,
    position: int,
    scope: Granularity,
    field_name: str,
) -> Mismatch | None:
    stats.total_fields += 1
    if _is_skip(c_item) or _is_skip(rust_item):
        stats.skipped_fields += 1
        return None
    stats.compared_fields += 1
    if not _items_equal(c_item, rust_item):
        return Mismatch(
            position=position,
            c_value=_item_repr(c_item),
            rust_value=_item_repr(rust_item),
            message=f"{field_name} mismatch at position {position}: {_item_repr(c_item)} vs {_item_repr(rust_item)}",
            suggested_scope=scope,
        )
    return None


def _is_ptr_arg(item: dict[str, Any]) -> bool:
    ty = item.get("ty")
    return isinstance(ty, str) and ty.startswith("ptr_")


def _is_len_arg(item: dict[str, Any]) -> bool:
    return item.get("ty") in {"i32", "i64", "isize", "u32", "u64", "usize"}


def _is_skip(item: dict[str, Any]) -> bool:
    return bool(item.get("skip"))


def _items_equal(c_item: dict[str, Any], rust_item: dict[str, Any]) -> bool:
    return c_item.get("ty") == rust_item.get("ty") and c_item.get("val") == rust_item.get("val")


def _item_repr(item: dict[str, Any]) -> str:
    return f"{item.get('ty')}={item.get('val')}"
