from __future__ import annotations

from c_rust.render.context_rules.base import (
    TailCompletionKind,
    block_tail_needs_todo,
    classify_block_tail,
)
from c_rust.render.groups import parse_rust


def _function_body(code: str):
    tree = parse_rust(code)
    for node in tree.root_node.named_children:
        if node.type != "function_item":
            continue
        body = node.child_by_field_name("body")
        assert body is not None
        return body
    raise AssertionError("function body not found")


def test_classify_block_tail_complete_expression() -> None:
    code = "fn foo() -> i32 { 1 }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.COMPLETE


def test_classify_block_tail_if_missing_else_closed_metadata() -> None:
    code = "fn foo(a: i32) -> i32 { if a > 0 { 1 } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.IF_MISSING_ELSE
    assert completion.if_consequence_start is not None
    assert completion.if_consequence_end is not None
    assert completion.if_in_consequence is False


def test_classify_block_tail_if_missing_else_in_consequence_metadata() -> None:
    code = "fn foo(a: i32) -> i32 { if a > 0 { 1 } }"
    end_byte = code.index("1") + 1
    completion = classify_block_tail(_function_body(code), end_byte=end_byte)
    assert completion.kind == TailCompletionKind.IF_MISSING_ELSE
    assert completion.if_in_consequence is True


def test_classify_block_tail_else_if_chain_reports_missing_final_else() -> None:
    code = "fn foo(a: i32, b: i32) -> i32 { if a > 0 { 1 } else if b > 0 { 2 } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.IF_MISSING_ELSE


def test_block_tail_needs_todo_compatibility_if_missing_else() -> None:
    code = "fn foo(a: i32) -> i32 { if a > 0 { 1 } }"
    assert block_tail_needs_todo(_function_body(code)) == (True, True)


def test_block_tail_needs_todo_compatibility_complete_tail() -> None:
    code = "fn foo() -> i32 { 1 }"
    assert block_tail_needs_todo(_function_body(code)) == (False, False)
