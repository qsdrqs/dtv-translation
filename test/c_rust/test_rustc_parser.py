from __future__ import annotations

from pathlib import Path

from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult
from c_rust.oracles.compiler_oracle.rustc_parser import has_errors, parse_rustc_diagnostics
from test.c_rust.utils import compile_rust


def test_rustc_parser_extracts_code_span() -> None:
    code = """\
fn foo() -> i32 {
    "hi"
}
"""
    byte_start = code.index('"hi"')
    byte_end = byte_start + len('"hi"')
    compile = compile_rust(code, error_format="json")
    result = RustcResult(
        stdout=compile.stdout,
        stderr=compile.stderr,
        exit_code=compile.returncode,
        elapsed_ms=0,
        command=("rustc",),
        source_path=Path("lib.rs"),
        output_path=Path("lib.rlib"),
        timed_out=False,
    )

    diagnostics = parse_rustc_diagnostics(result)
    assert has_errors(diagnostics)
    assert tuple(diag.message for diag in diagnostics) == (
        "mismatched types",
        "aborting due to 1 previous error",
        "For more information about this error, try `rustc --explain E0308`.",
    )
    assert tuple(diag.error_code for diag in diagnostics) == ("E0308", None, None)
    assert tuple(diag.severity for diag in diagnostics) == ("error", "error", "failure-note")

    diag = diagnostics[0]
    assert diag.span is not None
    assert diag.span[0] <= byte_start
    assert diag.span[1] >= byte_end


def test_rustc_parser_extracts_help_hints() -> None:
    code = """\
fn foo() -> i32 {
    if true { 1 }
}
"""
    compile = compile_rust(code, error_format="json")
    result = RustcResult(
        stdout=compile.stdout,
        stderr=compile.stderr,
        exit_code=compile.returncode,
        elapsed_ms=0,
        command=("rustc",),
        source_path=Path("lib.rs"),
        output_path=Path("lib.rlib"),
        timed_out=False,
    )

    diagnostics = parse_rustc_diagnostics(result)
    assert tuple(diag.message for diag in diagnostics) == (
        "`if` may be missing an `else` clause",
        "aborting due to 1 previous error",
        "For more information about this error, try `rustc --explain E0317`.",
    )
    assert tuple(diag.error_code for diag in diagnostics) == ("E0317", None, None)
    assert tuple(diag.severity for diag in diagnostics) == ("error", "error", "failure-note")
    hints = tuple(hint for diag in diagnostics for hint in diag.hints if hint.strip())
    assert hints == ("consider adding an `else` block that evaluates to the expected type",)
