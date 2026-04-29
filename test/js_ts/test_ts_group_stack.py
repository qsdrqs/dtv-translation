from __future__ import annotations

from tree_sitter_language_pack import get_parser

from core.llm_output import AssistantContent
from core.types import Granularity, GroupStackFrame
from js_ts.render.groups import ts_group_stack
from js_ts.render.renderer import JSToTSRenderer
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


def _full_stack_unstripped(prefix: str, suffix: str = "") -> tuple[GroupStackFrame, ...]:
    """Mirror JSToTSRenderer: pass full prefix byte length, do NOT rstrip.

    Required to reproduce the renderer's actual cursor position; the other
    helpers strip trailing whitespace and therefore do not exercise the
    production path.
    """
    code = f"{prefix}{suffix}"
    end_byte = len(prefix.encode("utf-8"))
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


def test_cursor_at_class_boundary_no_toplevel_block() -> None:
    """When the cursor is exactly at the closing } of a top-level class,
    no toplevel block should be created. The boundary checkpoint (closing brace)
    must not be claimed by any group so BLOCK rollback preserves it."""
    prefix = """\
class Foo {
    prop: number = 1;
}
"""
    result = _stack(prefix)
    assert len(result) == 0


def test_cursor_past_class_creates_toplevel_block_at_class_end() -> None:
    """After a top-level class has closed and the cursor is past it,
    a toplevel block should start at the class end."""
    prefix = """\
class Foo {
    prop: number = 1;
}
const x: number = 1;
"""
    stack = _full_stack(prefix)
    assert len(stack) == 1
    assert stack[0].kind == Granularity.BLOCK
    assert stack[0].group_id == "toplevel_block@35"


def test_export_class_is_block_separator() -> None:
    prefix = """\
export class Bar {}
const x: number = 1;
"""
    stack = _full_stack(prefix)
    assert len(stack) == 1
    assert stack[0].kind == Granularity.BLOCK
    assert stack[0].group_id != "toplevel_block@0"


def test_abstract_class_is_block_separator() -> None:
    prefix = """\
abstract class Baz {}
const x: number = 1;
"""
    stack = _full_stack(prefix)
    assert len(stack) == 1
    assert stack[0].kind == Granularity.BLOCK
    assert stack[0].group_id != "toplevel_block@0"


def test_block_rollback_after_class_preserves_closing_brace() -> None:
    """BLOCK rollback at top level must preserve the class closing brace.

    After a class is fully closed, the boundary checkpoint (containing })
    should be outside the toplevel block, so BLOCK rollback does not discard it.
    """
    m = RollbackManager()

    prefix_class_body = (
        "class Foo {\n"
        "    prop: number = 1;\n"
    )
    prefix_class_closed = (
        "class Foo {\n"
        "    prop: number = 1;\n"
        "}\n"
    )
    prefix_after = (
        "class Foo {\n"
        "    prop: number = 1;\n"
        "}\n"
        "const x: number = 1;\n"
    )

    stack_body = _full_stack(prefix_class_body, "\n}\nconst x: number = 1;\n")
    stack_closed = _full_stack(prefix_class_closed)
    stack_after = _full_stack(prefix_after)

    _commit(m, prefix_class_body, stack_body)
    _commit(m, prefix_class_closed, stack_closed)
    _commit(m, prefix_after, stack_after)

    assert any(f.kind == Granularity.BLOCK for f in m.group_stack)

    out = m.rollback(Granularity.BLOCK)
    assert out.code_prefix == prefix_class_closed
    assert [c.code_prefix for c in m.stmt_checkpoints] == [
        prefix_class_body,
        prefix_class_closed,
    ]


def test_block_rollback_after_function_returns_to_function_end() -> None:
    """Simulates the smoke test commit sequence.

    Commit: import (top-level block 0 on import, inside FUNC for body)
    Commit: function body stmts (FUNC)
    Commit: function closed (boundary -- no toplevel block)
    Commit: top-level stmt after function (toplevel block 1)
    Commit: another top-level stmt (same block 1)

    BLOCK rollback should discard only the top-level stmts after
    the function, preserving the function's closing } checkpoint.
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

    out = m.rollback(Granularity.BLOCK)
    # BLOCK rollback truncates to start_stmt=3 (toplevel block opened after
    # function closed). Checkpoints 0-2 (import, func body, func close) are
    # preserved; checkpoints 3-4 (top-level stmts) are discarded.
    assert out.code_prefix == prefix_func_end
    assert [c.code_prefix for c in m.stmt_checkpoints] == [
        prefix_import,
        prefix_func_s1,
        prefix_func_end,
    ]


def test_no_toplevel_block_at_class_close_with_trailing_whitespace_unstripped() -> None:
    prefix = "class A {\n  m(): void {}\n}\n"
    stack = _full_stack_unstripped(prefix)
    assert len(stack) == 0


def test_no_toplevel_block_at_function_close_with_trailing_whitespace_unstripped() -> None:
    prefix = "function f(): void {\n  return;\n}\n\n"
    stack = _full_stack_unstripped(prefix)
    assert len(stack) == 0


def test_toplevel_block_emitted_when_real_content_past_declaration_unstripped() -> None:
    prefix = "class A {\n  m(): void {}\n}\nconst x: number = 1;\n"
    stack = _full_stack_unstripped(prefix)
    assert len(stack) == 1
    assert stack[0].kind == Granularity.BLOCK


def test_renderer_emits_no_toplevel_block_at_class_close_boundary() -> None:
    prefix = "class A {\n  m(): void {}\n}\n"
    result = JSToTSRenderer().try_render(prefix)
    assert result.artifact is not None
    assert result.artifact.group_stack is not None
    assert all(f.kind != Granularity.BLOCK for f in result.artifact.group_stack)


def test_renderer_emits_toplevel_block_when_stmt_past_class() -> None:
    prefix = "class A {\n  m(): void {}\n}\nconst x: number = 1;\n"
    result = JSToTSRenderer().try_render(prefix)
    assert result.artifact is not None
    assert result.artifact.group_stack is not None
    block_frames = [f for f in result.artifact.group_stack if f.kind == Granularity.BLOCK]
    assert len(block_frames) == 1


def test_block_rollback_via_renderer_preserves_class_close_brace() -> None:
    renderer = JSToTSRenderer()
    prefix_inside_class = "class A {\n  m(): void {\n    return;\n  }\n"
    prefix_class_closed = prefix_inside_class + "}\n"

    art_inside = renderer.try_render(prefix_inside_class).artifact
    art_closed = renderer.try_render(prefix_class_closed).artifact
    assert art_inside is not None
    assert art_closed is not None
    assert art_inside.group_stack is not None
    assert art_closed.group_stack is not None

    m = RollbackManager()
    _commit(m, prefix_inside_class, art_inside.group_stack)
    _commit(m, prefix_class_closed, art_closed.group_stack)

    out = m.rollback(Granularity.BLOCK)
    assert out.code_prefix.rstrip().endswith("}")
    assert out.code_prefix == prefix_class_closed
