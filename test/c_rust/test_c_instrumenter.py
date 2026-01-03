from __future__ import annotations

from c_rust.oracles.function_diff_test_oracle.c_instrumenter import (
    instrument_c_functions,
)


def test_c_single_line_return_wrapped() -> None:
    source = "int f(){return 1;}"
    instrumented = instrument_c_functions(source)

    assert 'dtv_trace_function_enter("f")' in instrumented
    assert instrumented.count('dtv_trace_function_exit("f")') == 1
    assert '{ dtv_trace_function_exit("f"); return 1; }' in instrumented


def test_c_multiple_returns_single_line() -> None:
    source = "int f(int x){ if (x) return 1; return 2; }"
    instrumented = instrument_c_functions(source)

    assert instrumented.count('dtv_trace_function_exit("f")') == 2
    assert 'if (x) { dtv_trace_function_exit("f"); return 1; }' in instrumented
    assert '{ dtv_trace_function_exit("f"); return 2; }' in instrumented


def test_c_if_else_with_braces() -> None:
    source = "int f(int x){ if (x) return 1; else { return 2; } }"
    instrumented = instrument_c_functions(source)

    assert instrumented.count('dtv_trace_function_exit("f")') == 2
    assert 'if (x) { dtv_trace_function_exit("f"); return 1; }' in instrumented
    assert 'else { { dtv_trace_function_exit("f"); return 2; } }' in instrumented


def test_c_switch_case_returns() -> None:
    source = "int f(int x){ switch(x){ case 1: return 1; default: return 0; } }"
    instrumented = instrument_c_functions(source)

    assert instrumented.count('dtv_trace_function_exit("f")') == 2
    assert 'case 1: { dtv_trace_function_exit("f"); return 1; }' in instrumented
    assert 'default: { dtv_trace_function_exit("f"); return 0; }' in instrumented


def test_c_no_return_inserts_exit_before_close() -> None:
    source = "int f(int x){ int y = x + 1; }"
    instrumented = instrument_c_functions(source)

    assert instrumented.count('dtv_trace_function_exit("f")') == 1
    assert instrumented.index("int y = x + 1;") < instrumented.index(
        'dtv_trace_function_exit("f")'
    )
    assert instrumented.index('dtv_trace_function_exit("f")') < instrumented.rindex("}")


def test_c_target_function_emits_args_and_ret() -> None:
    source = """
struct S { int x; };
int f(int *p, float x, struct S s) { return 1; }
int g() { return 0; }
"""
    instrumented = instrument_c_functions(source, target_function="f")

    assert 'dtv_trace_function_enter_args("f"' in instrumented
    assert 'dtv_trace_function_exit_ret("f"' in instrumented
    assert 'dtv_trace_function_enter("g")' in instrumented
    assert 'dtv_trace_function_exit("g")' in instrumented
    assert "dtv_json_array_push_unsupported" in instrumented
    assert "__dtv_ptr_args" in instrumented
