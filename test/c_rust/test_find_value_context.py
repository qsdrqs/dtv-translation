from __future__ import annotations

from c_rust.render.context_rules.base import (
    ValueContextInfo,
    ValueContextReason,
    find_value_context,
)
from c_rust.render.groups import parse_rust


def _first_node_of_type(code: str, node_type: str):
    tree = parse_rust(code)
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == node_type:
            return n
        stack.extend(reversed(n.children))
    raise AssertionError(f"no {node_type!r} node in: {code!r}")


def _first_integer(code: str):
    return _first_node_of_type(code, "integer_literal")


def _bytes(code: str) -> bytes:
    return code.encode("utf-8")


def test_direct_let_initializer_is_value_context() -> None:
    code = "fn foo() { let x: i32 = 42; }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.LET)


def test_direct_return_expression_is_value_context() -> None:
    code = "fn foo() -> i32 { return 42; }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.RETURN)


def test_call_argument_is_value_context() -> None:
    code = "fn foo() { f(42); }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.ARGUMENT)


def test_assignment_rhs_is_value_context() -> None:
    code = "fn foo() { let mut x = 0; x = 42; }"
    ints = [
        n for n in _walk(parse_rust(code).root_node)
        if n.type == "integer_literal"
    ]
    assert [_bytes(code)[n.start_byte:n.end_byte] for n in ints] == [b"0", b"42"]
    info = find_value_context(ints[1], _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.ASSIGNMENT)


def test_unsafe_block_tail_propagates_to_let_initializer() -> None:
    code = "fn foo() { let x: i32 = unsafe { 42 }; }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.LET)


def test_nested_wrappers_tail_propagates_to_let_initializer() -> None:
    code = "fn foo() { let x: i32 = unsafe { { 42 } }; }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.LET)


def test_fn_body_tail_with_return_type_is_value_context() -> None:
    code = "fn foo() -> i32 { 42 }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.FN_BODY_TAIL)


def test_fn_body_tail_without_return_type_is_not_value_context() -> None:
    code = "fn foo() { 42 }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info is None


def test_fn_body_non_tail_statement_is_not_value_context() -> None:
    # `42;` is an expression_statement with semicolon - value is discarded.
    code = "fn foo() -> i32 { 42; 0 }"
    ints = [
        n for n in _walk(parse_rust(code).root_node)
        if n.type == "integer_literal"
    ]
    assert [_bytes(code)[n.start_byte:n.end_byte] for n in ints] == [b"42", b"0"]
    info = find_value_context(ints[0], _bytes(code))
    assert info is None


def test_wrapper_non_tail_position_does_not_propagate() -> None:
    # `42;` inside unsafe block - semicolon-terminated, value discarded.
    code = "fn foo() -> i32 { unsafe { 42; 0 } }"
    ints = [
        n for n in _walk(parse_rust(code).root_node)
        if n.type == "integer_literal"
    ]
    info = find_value_context(ints[0], _bytes(code))
    assert info is None


def test_wrapper_tail_propagates_to_fn_body_tail() -> None:
    code = "fn foo() -> i32 { unsafe { 42 } }"
    info = find_value_context(_first_integer(code), _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.FN_BODY_TAIL)


def test_while_body_tail_is_not_value_context() -> None:
    # LOOPING blocks propagation - while body is not a value context
    # even if the outer fn demands i32.
    code = "fn foo() -> i32 { while false { 42 } 0 }"
    ints = [
        n for n in _walk(parse_rust(code).root_node)
        if n.type == "integer_literal"
    ]
    info = find_value_context(ints[0], _bytes(code))
    assert info is None


def test_match_arm_value_when_match_is_fn_body_tail() -> None:
    code = "fn foo() -> i32 { match 0 { _ => 42 } }"
    ints = [
        n for n in _walk(parse_rust(code).root_node)
        if n.type == "integer_literal"
    ]
    assert [_bytes(code)[n.start_byte:n.end_byte] for n in ints] == [b"0", b"42"]
    info = find_value_context(ints[1], _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.MATCH_ARM_VALUE)


def test_match_arm_value_when_match_is_statement_is_not_value_context() -> None:
    code = "fn foo() { match 0 { _ => 42 }; }"
    ints = [
        n for n in _walk(parse_rust(code).root_node)
        if n.type == "integer_literal"
    ]
    info = find_value_context(ints[1], _bytes(code))
    assert info is None


def test_if_consequence_tail_in_fn_body_tail_is_value_context() -> None:
    code = "fn foo() -> i32 { if true { 42 } else { 0 } }"
    ints = [
        n for n in _walk(parse_rust(code).root_node)
        if n.type == "integer_literal"
    ]
    info = find_value_context(ints[0], _bytes(code))
    assert info == ValueContextInfo(reason=ValueContextReason.FN_BODY_TAIL)


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))
