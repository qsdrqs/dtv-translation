from __future__ import annotations

from c_rust.oracles.function_diff_test_oracle.rust_instrumenter import (
    instrument_rust_functions,
)


def test_rust_explicit_return_wrapped() -> None:
    source = "fn f() -> i32 { return 1; }"
    instrumented = instrument_rust_functions(source)

    assert '{ trace_function_exit("f"); return 1 }' in instrumented
    assert instrumented.count('trace_function_exit("f")') == 1


def test_rust_explicit_return_and_implicit_tail() -> None:
    source = "fn f(x: i32) -> i32 { if x > 0 { return 1; } 2 /* tail */ }"
    instrumented = instrument_rust_functions(source)

    assert '{ trace_function_exit("f"); return 1 }' in instrumented
    assert 'trace_function_exit("f"); 2' in instrumented
    assert instrumented.count('trace_function_exit("f")') == 2


def test_rust_match_arm_return_and_tail() -> None:
    source = "fn f(x: i32) -> i32 { match x { 0 => return 1, _ => 2 } }"
    instrumented = instrument_rust_functions(source)

    assert '=> { trace_function_exit("f"); return 1 }' in instrumented
    assert 'trace_function_exit("f"); match x' in instrumented
    assert instrumented.count('trace_function_exit("f")') == 2


def test_rust_closure_async_returns_ignored() -> None:
    source = (
        "fn f() -> i32 { let c = || { return 1; }; let g = async { return 2; }; 3 }"
    )
    instrumented = instrument_rust_functions(source)

    assert instrumented.count('trace_function_exit("f")') == 1
    assert 'trace_function_exit("f"); return 1' not in instrumented
    assert 'trace_function_exit("f"); return 2' not in instrumented
    assert 'trace_function_exit("f"); 3' in instrumented


def test_rust_target_function_emits_args_and_ret() -> None:
    source = """
fn f(p: *const i32, s: &[i32], arr: [i32; 2]) -> i32 { return 1; }
fn g() -> i32 { return 0; }
"""
    instrumented = instrument_rust_functions(source, target_function="f")

    assert 'trace_function_enter_args("f"' in instrumented
    assert 'trace_function_exit_ret("f"' in instrumented
    assert 'trace_function_enter("g")' in instrumented
    assert 'trace_function_exit("g")' in instrumented
    assert "json_value_slice_i32" in instrumented
    assert "json_value_raw_ptr_i32" in instrumented
    assert "json_value_array_i32" in instrumented
