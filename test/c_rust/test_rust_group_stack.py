from __future__ import annotations

from c_rust.render import CRustRenderer
from c_rust.render.groups import parse_rust, rust_group_stack
from core.types import Granularity, RenderStatus


def _stack(prefix: str, suffix: str = "") -> tuple[Granularity, ...]:
    code = f"{prefix}{suffix}"
    end_byte = len(prefix.rstrip().encode("utf-8"))
    tree = parse_rust(code)
    stack = rust_group_stack(
        tree,
        prefix_end_byte=end_byte,
        source_bytes=code.encode("utf-8"),
        skip_function_body_block=True,
    )
    return tuple(frame.kind for frame in stack)


def _render_stack(prefix: str) -> tuple[Granularity, ...] | None:
    renderer = CRustRenderer()
    result = renderer.try_render(prefix, Granularity.STMT)
    if result.status != RenderStatus.OK or result.artifact is None:
        return None
    stack = result.artifact.group_stack
    if stack is None:
        return None
    return tuple(frame.kind for frame in stack)


def test_stack_inside_block() -> None:
    prefix = """\
fn foo() {
  if cond {
    s1;
"""
    suffix = """\
  }
}
"""
    assert _stack(prefix, suffix) == (Granularity.FUNC, Granularity.BLOCK)


def test_stack_after_block_close() -> None:
    prefix = """\
fn foo() {
  if cond {
    s1;
  }
"""
    suffix = """\
  s2;
}
"""
    assert _stack(prefix, suffix) == (Granularity.FUNC,)


def test_stack_includes_function_name() -> None:
    prefix = """\
fn foo() {
  s1;
"""
    suffix = """\
}
"""
    code = f"{prefix}{suffix}"
    end_byte = len(prefix.rstrip().encode("utf-8"))
    tree = parse_rust(code)
    stack = rust_group_stack(
        tree,
        prefix_end_byte=end_byte,
        source_bytes=code.encode("utf-8"),
        skip_function_body_block=True,
    )
    assert stack
    assert any(frame.kind == Granularity.FUNC and frame.name_id == "foo" for frame in stack)


def test_stack_after_function_end() -> None:
    prefix = """\
fn foo() {
  s1;
}
"""
    assert _stack(prefix) == ()


def test_stack_trailing_whitespace_matches_trimmed() -> None:
    prefix = """\
fn foo() {
  if cond {
    s1;
"""
    suffix = """\
  }
}
"""
    prefix_with_ws = prefix + "   \n\n  "
    expected = (Granularity.FUNC, Granularity.BLOCK)
    assert _stack(prefix, suffix) == expected
    assert _stack(prefix_with_ws, suffix) == expected


def test_renderer_group_stack_inside_block() -> None:
    prefix = """\
fn foo() {
  if cond {
    s2;
"""
    assert _render_stack(prefix) == (Granularity.FUNC, Granularity.BLOCK)

