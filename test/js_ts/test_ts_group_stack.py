from __future__ import annotations

from tree_sitter_language_pack import get_parser

from core.llm_output import AssistantContent
from core.types import Granularity, GroupStackFrame, RollbackScope
from js_ts.render.groups import ts_group_stack
from rollback.manager import RollbackManager

_TS_PARSER = get_parser("typescript")


def _stack(prefix: str, suffix: str = "") -> tuple[Granularity, ...]:
    code = f"{prefix}{suffix}"
    end_byte = len(prefix.rstrip().encode("utf-8"))
    tree = _TS_PARSER.parse(code.encode("utf-8"))
    stack = ts_group_stack(
        tree,
        prefix_end_byte=end_byte,
        source_bytes=code.encode("utf-8"),
    )
    return tuple(frame.kind for frame in stack)


def _full_stack(prefix: str, suffix: str = "") -> tuple[GroupStackFrame, ...]:
    code = f"{prefix}{suffix}"
    end_byte = len(prefix.rstrip().encode("utf-8"))
    tree = _TS_PARSER.parse(code.encode("utf-8"))
    return ts_group_stack(
        tree,
        prefix_end_byte=end_byte,
        source_bytes=code.encode("utf-8"),
    )


# Inside function

def test_inside_function_body() -> None:
    prefix = """\
function foo() {
    const x: number = 1;
"""
    assert _stack(prefix, "}\n") == (Granularity.FUNC,)


def test_inside_nested_block_in_function() -> None:
    prefix = """\
function foo() {
    if (true) {
        const x: number = 1;
"""
    assert _stack(prefix, "}\n}\n") == (Granularity.FUNC, Granularity.BLOCK)


# Top-level: after function

def test_toplevel_after_function() -> None:
    """Top-level statements after a function declaration form a BLOCK."""
    prefix = """\
function foo(): void {
    return;
}
const x: number = 1;
"""
    assert _stack(prefix) == (Granularity.BLOCK,)


def test_toplevel_after_function_multiple_stmts() -> None:
    """Multiple top-level stmts after a function are in the same BLOCK."""
    prefix = """\
function foo(): void {
    return;
}
const x: number = 1;
const y: number = 2;
"""
    assert _stack(prefix) == (Granularity.BLOCK,)


def test_toplevel_after_function_same_block_id() -> None:
    """Growing the prefix within the same top-level chunk keeps the same block group_id."""
    prefix_short = """\
function foo(): void {
    return;
}
const x: number = 1;
"""
    prefix_long = """\
function foo(): void {
    return;
}
const x: number = 1;
const y: number = 2;
"""
    stack_short = _full_stack(prefix_short)
    stack_long = _full_stack(prefix_long)
    assert len(stack_short) == 1
    assert len(stack_long) == 1
    assert stack_short[0].kind == Granularity.BLOCK
    assert stack_long[0].kind == Granularity.BLOCK
    assert stack_short[0].group_id == stack_long[0].group_id


# Top-level: before function

def test_toplevel_before_function() -> None:
    """Top-level statements before the first function form a BLOCK."""
    prefix = """\
import * as readline from 'readline';
"""
    suffix = """\
function foo(): void {
    return;
}
"""
    assert _stack(prefix, suffix) == (Granularity.BLOCK,)


# Top-level: two functions separate blocks

def test_toplevel_between_functions() -> None:
    """A function separates top-level code into distinct BLOCKs.

    Cursor is after the second function, so it should be in a new BLOCK
    distinct from the pre-function BLOCK.
    """
    prefix = """\
const a: number = 1;
function foo(): void {
    return;
}
const b: number = 2;
"""
    stack = _full_stack(prefix)
    assert len(stack) == 1
    assert stack[0].kind == Granularity.BLOCK


def test_toplevel_blocks_differ_across_function_boundary() -> None:
    """Blocks before and after a function must have different group_ids."""
    before_func = """\
const a: number = 1;
"""
    after_func = """\
const a: number = 1;
function foo(): void {
    return;
}
const b: number = 2;
"""
    suffix = """\
function foo(): void {
    return;
}
"""
    stack_before = _full_stack(before_func, suffix)
    stack_after = _full_stack(after_func)
    assert len(stack_before) == 1 and stack_before[0].kind == Granularity.BLOCK
    assert len(stack_after) == 1 and stack_after[0].kind == Granularity.BLOCK
    assert stack_before[0].group_id != stack_after[0].group_id


# Top-level: cursor inside function

def test_inside_function_no_toplevel_block() -> None:
    """When cursor is inside a function, no top-level BLOCK should appear."""
    prefix = """\
const a: number = 1;
function foo(): void {
    const x: number = 1;
"""
    assert _stack(prefix, "}\n") == (Granularity.FUNC,)


# Arrow function does not split blocks

def test_arrow_function_assignment_does_not_split() -> None:
    """Arrow functions assigned to variables are top-level stmts, not block separators."""
    prefix = """\
const helper = (x: number): number => {
    return x + 1;
};
const y: number = helper(1);
"""
    stack = _full_stack(prefix)
    # helper and y are in the same top-level BLOCK (arrow doesn't split)
    assert len(stack) == 1
    assert stack[0].kind == Granularity.BLOCK


# Smoke test scenario

def test_smoke_scenario_toplevel_after_trap() -> None:
    """Reproduces the smoke test layout: import, function, then top-level IO code."""
    prefix = """\
import * as readline from 'readline';

function trap(height: number[]): number {
    const n: number = height.length;
    if (n < 3) return 0;
    return 0;
}

const input: string = "";
"""
    stack = _full_stack(prefix)
    assert len(stack) == 1
    assert stack[0].kind == Granularity.BLOCK


# Integration: group stack + rollback

def _commit(m: RollbackManager, prefix: str, group_stack: tuple[GroupStackFrame, ...]) -> None:
    m.sync_groups(group_stack)
    m.add_stmt_checkpoint(prefix, AssistantContent.empty(), None)


def test_block_rollback_after_function_returns_to_function_end() -> None:
    """Simulates the smoke test commit sequence.

    Commit: import (top-level block 0)
    Commit: function body stmts (FUNC)
    Commit: function closed, top-level stmt after function (top-level block 1)
    Commit: another top-level stmt (same block 1)

    BLOCK rollback should discard the top-level stmts after the function
    but keep the import and function commits.
    """
    m = RollbackManager()

    prefix_import = "import * as readline from 'readline';\n"
    prefix_func_s1 = prefix_import + "function trap(): number {\n  const n: number = 1;\n"
    prefix_func_end = prefix_import + "function trap(): number {\n  return 0;\n}\n"
    prefix_toplevel_s1 = prefix_func_end + "const input: string = '';\n"
    prefix_toplevel_s2 = prefix_toplevel_s1 + "const rl: number = 1;\n"

    stack_import = _full_stack(prefix_import, "function trap(): number {\n  return 0;\n}\n")
    stack_in_func = _full_stack(prefix_func_s1, "  return 0;\n}\n")
    stack_func_closed = _full_stack(prefix_func_end)
    stack_toplevel_s1 = _full_stack(prefix_toplevel_s1)
    stack_toplevel_s2 = _full_stack(prefix_toplevel_s2)

    _commit(m, prefix_import, stack_import)
    _commit(m, prefix_func_s1, stack_in_func)
    _commit(m, prefix_func_end, stack_func_closed)
    _commit(m, prefix_toplevel_s1, stack_toplevel_s1)
    _commit(m, prefix_toplevel_s2, stack_toplevel_s2)

    assert any(f.kind == Granularity.BLOCK for f in m.group_stack)

    out = m.rollback(RollbackScope.BLOCK)
    # BLOCK rollback truncates to start_stmt=2, keeping checkpoints 0 and 1.
    # prefix_func_end was committed after the top-level block opened (cursor
    # was already at top level when the function's closing } was committed),
    # so it falls inside the block and gets discarded together with the
    # later top-level stmts.
    assert out.code_prefix == prefix_func_s1
    assert [c.code_prefix for c in m.stmt_checkpoints] == [
        prefix_import,
        prefix_func_s1,
    ]
