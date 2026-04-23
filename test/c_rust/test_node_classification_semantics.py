from __future__ import annotations

import pytest

from c_rust.render.context_rules.base import NODE_CLASSIFICATION, NodeKind
from test.c_rust.utils import compile_rust


# Concrete Rust syntax used to exercise each classified node type as a
# function-body tail expression. A test-only fixture; keeping it separate
# from NODE_CLASSIFICATION lets the meta-test (Layer A) guarantee coverage
# while these semantic tests exercise only the kinds that have a well-defined
# rustc-visible contract.
_TAIL_FORWARDING_SYNTAX: dict[str, str] = {
    "block":                    "{ 1 }",
    "unsafe_block":             "unsafe { 1 }",
    "const_block":              "const { 1 }",
    "parenthesized_expression": "(1)",
}
_TAIL_FORWARDING_EXCLUDED: dict[str, str] = {}


_LOOPING_SYNTAX: dict[str, str] = {
    "for_expression":   "for _ in 0..1 {}",
    "while_expression": "while false {}",
}
_LOOPING_EXCLUDED: dict[str, str] = {
    "loop_expression": "produces `!` (divergent); coerces to any type, so fn-tail probe cannot observe the shape contract",
}


_CONTROL_LEAF_EXCLUDED: dict[str, str] = {
    "break_expression":    "cannot appear at fn top level; shape contract covered by find_value_context tests",
    "continue_expression": "cannot appear at fn top level; shape contract covered by find_value_context tests",
}


_VALUE_WRAPPING_SYNTAX: dict[str, str] = {
    "async_block": "async { 1i32 }",
}
_VALUE_WRAPPING_EXCLUDED: dict[str, str] = {
    "try_block": "nightly-gated (#![feature(try_blocks)]); local rustc may not accept",
    "gen_block": "nightly-gated (#![feature(gen_blocks)]); local rustc may not accept",
}


def _resolve_fixture(
    node_type: str,
    syntax_map: dict[str, str],
    excluded_map: dict[str, str],
    kind_name: str,
) -> str:
    if node_type in syntax_map:
        return syntax_map[node_type]
    if node_type in excluded_map:
        pytest.skip(f"{node_type}: {excluded_map[node_type]}")
    pytest.fail(
        f"{kind_name} node type {node_type!r} has neither a rustc fixture nor "
        f"an explicit exclusion reason. Add it to the corresponding _SYNTAX or "
        f"_EXCLUDED map in this file, or reclassify it in NODE_CLASSIFICATION."
    )


def _types_in_kind(kind: NodeKind) -> list[str]:
    return sorted(t for t, k in NODE_CLASSIFICATION.items() if k == kind)


@pytest.mark.parametrize("node_type", _types_in_kind(NodeKind.TAIL_FORWARDING))
def test_tail_forwarding_preserves_inner_tail_type(node_type: str) -> None:
    syntax = _resolve_fixture(
        node_type, _TAIL_FORWARDING_SYNTAX, _TAIL_FORWARDING_EXCLUDED, "TAIL_FORWARDING"
    )
    code = f"fn foo() -> i32 {{ {syntax} }}"
    result = compile_rust(code)
    assert result.ok, (
        f"TAIL_FORWARDING contract violated: {node_type} wrapping i32 tail "
        f"did not type-check as i32. rustc stderr:\n{result.stderr}"
    )


@pytest.mark.parametrize("node_type", _types_in_kind(NodeKind.LOOPING))
def test_looping_cannot_produce_typed_value(node_type: str) -> None:
    syntax = _resolve_fixture(
        node_type, _LOOPING_SYNTAX, _LOOPING_EXCLUDED, "LOOPING"
    )
    code = f"fn foo() -> i32 {{ {syntax} }}"
    result = compile_rust(code)
    assert not result.ok, (
        f"LOOPING contract violated: {node_type} unexpectedly "
        f"type-checked as i32 fn tail."
    )


@pytest.mark.parametrize("node_type", _types_in_kind(NodeKind.CONTROL_LEAF))
def test_control_leaf_cannot_appear_at_fn_top_level(node_type: str) -> None:
    _resolve_fixture(node_type, {}, _CONTROL_LEAF_EXCLUDED, "CONTROL_LEAF")


@pytest.mark.parametrize("node_type", _types_in_kind(NodeKind.VALUE_WRAPPING))
def test_value_wrapping_changes_inner_type(node_type: str) -> None:
    syntax = _resolve_fixture(
        node_type, _VALUE_WRAPPING_SYNTAX, _VALUE_WRAPPING_EXCLUDED, "VALUE_WRAPPING"
    )
    code = f"fn foo() -> i32 {{ {syntax} }}"
    result = compile_rust(code)
    assert not result.ok, (
        f"VALUE_WRAPPING contract violated: {node_type} unexpectedly "
        f"type-checked as i32 fn tail (expected a wrapped type)."
    )
