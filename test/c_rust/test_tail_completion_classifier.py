from __future__ import annotations

from c_rust.render.context_rules.base import (
    _FN_TAIL_DOWNGRADE_KINDS,
    NODE_CLASSIFICATION,
    NodeKind,
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


def test_classify_block_tail_unsafe_block_with_if_missing_else() -> None:
    # fn body tail `unsafe { if cond { 1 } }` -> unsafe block forwards tail value.
    # Inner `if` has no else, so the whole tail evaluates to `()` instead of i32.
    # Classifier must look through unsafe_block to the inner if.
    code = "fn foo(a: i32) -> i32 { unsafe { if a > 0 { 1 } } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.IF_MISSING_ELSE
    assert completion.if_consequence_start is not None
    assert completion.if_consequence_end is not None
    consequence_bytes = code.encode("utf-8")[
        completion.if_consequence_start:completion.if_consequence_end
    ]
    assert consequence_bytes == b"{ 1 }"


def test_classify_block_tail_unsafe_block_complete_tail() -> None:
    # Regression guard: non-if tail inside unsafe block should stay COMPLETE.
    code = "fn foo() -> i32 { unsafe { 42 } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.COMPLETE


def test_classify_block_tail_naked_block_with_if_missing_else() -> None:
    # fn body tail `{ if cond { 1 } }` - naked block also forwards tail value.
    code = "fn foo(a: i32) -> i32 { { if a > 0 { 1 } } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.IF_MISSING_ELSE
    assert completion.if_consequence_start is not None
    consequence_bytes = code.encode("utf-8")[
        completion.if_consequence_start:completion.if_consequence_end
    ]
    assert consequence_bytes == b"{ 1 }"


def test_classify_block_tail_nested_wrappers_if_missing_else() -> None:
    # Nested `unsafe { unsafe { if ... } }`: classifier must recurse through each
    # wrapper layer and surface the innermost `if`'s consequence metadata.
    code = "fn foo(a: i32) -> i32 { unsafe { unsafe { if a > 0 { 1 } } } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.IF_MISSING_ELSE
    assert completion.if_consequence_start is not None
    consequence_bytes = code.encode("utf-8")[
        completion.if_consequence_start:completion.if_consequence_end
    ]
    assert consequence_bytes == b"{ 1 }"


def test_classify_block_tail_if_expr_as_fn_tail_downgrades() -> None:
    # if/match as tail expression: always NEEDS_SEMI_TODO. Renderer prefers
    # loud failure (must_use warning visible to oracle) over silent misjudge.
    code = "fn foo(a: i32) -> i32 { unsafe { if a > 0 { 1 } else { 2 } } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.NEEDS_SEMI_TODO


def test_classify_block_tail_loop_expr_as_fn_tail_downgrades() -> None:
    # `loop { break X }` yields X; `loop { break }` yields (). Either way, when
    # it lands at fn tail of a non-() return, downgrade for compile-safety.
    code = "fn foo() -> i32 { loop { break 1; } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.NEEDS_SEMI_TODO


def test_fn_tail_downgrade_set_matches_node_classification() -> None:
    # Lock the binding: every LOOPING/BRANCHING node has a fn-tail fixture
    # and downgrades. Catches new grammar nodes on tree-sitter upgrade.
    fixtures = {
        "while_expression": "while true {}",
        "for_expression":   "for _ in 0..1 {}",
        "loop_expression":  "loop {}",
        "if_expression":    "if true { 1 } else { 2 }",
        "match_expression": "match 1 { _ => 1 }",
    }
    expected = frozenset(
        node_type
        for node_type, kind in NODE_CLASSIFICATION.items()
        if kind in _FN_TAIL_DOWNGRADE_KINDS
    )
    missing = expected - frozenset(fixtures)
    assert missing == frozenset(), f"Add fn-tail fixture for: {sorted(missing)}"
    for node_type in expected:
        code = f"fn foo() -> i32 {{ {fixtures[node_type]} }}"
        completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
        assert completion.kind == TailCompletionKind.NEEDS_SEMI_TODO, node_type


def test_classify_block_tail_wrapper_middle_if_not_tail_stays_complete() -> None:
    # Sanity: if inside wrapper is not at the wrapper's tail position -> COMPLETE.
    code = "fn foo() -> i32 { unsafe { if true { 1; }; 42 } }"
    completion = classify_block_tail(_function_body(code), end_byte=len(code.encode("utf-8")))
    assert completion.kind == TailCompletionKind.COMPLETE
