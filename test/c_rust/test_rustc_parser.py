from __future__ import annotations

from pathlib import Path

from c_rust.oracles.compiler_oracle.compiler_oracle import (
    _decide_verdict,
    _filter_partial_noise,
)
from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult
from c_rust.oracles.compiler_oracle.rustc_parser import has_errors, parse_rustc_diagnostics
from core.types import Diagnostic, Verdict
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


# -- _filter_partial_noise tests --


def test_filter_partial_noise_removes_e0425_and_orphaned_summary() -> None:
    diagnostics = (
        Diagnostic(message="cannot find function `foo`", error_code="E0425"),
        Diagnostic(message="aborting due to 1 previous error", error_code=None),
    )
    filtered = _filter_partial_noise(diagnostics)
    assert filtered == ()


def test_filter_partial_noise_removes_e0412_and_e0433() -> None:
    diagnostics = (
        Diagnostic(message="cannot find type `Foo`", error_code="E0412"),
        Diagnostic(message="use of undeclared crate or module", error_code="E0433"),
    )
    filtered = _filter_partial_noise(diagnostics)
    assert filtered == ()


def test_filter_partial_noise_keeps_real_errors() -> None:
    diagnostics = (
        Diagnostic(message="cannot find function `foo`", error_code="E0425"),
        Diagnostic(message="mismatched types", error_code="E0308"),
    )
    filtered = _filter_partial_noise(diagnostics)
    assert filtered == (
        Diagnostic(message="mismatched types", error_code="E0308"),
    )


def test_filter_partial_noise_keeps_warnings() -> None:
    diagnostics = (
        Diagnostic(message="unused variable", severity="warning", error_code="unused_variables"),
    )
    filtered = _filter_partial_noise(diagnostics)
    assert filtered == diagnostics


# -- _decide_verdict tests with filtering --


def test_decide_verdict_pass_after_noise_filtered() -> None:
    assert _decide_verdict(exit_code=1, diagnostics=(), timed_out=False) == Verdict.FAIL


def test_decide_verdict_pass_when_only_warnings_remain() -> None:
    diagnostics = (
        Diagnostic(message="unused variable", severity="warning"),
    )
    assert _decide_verdict(exit_code=0, diagnostics=diagnostics, timed_out=False) == Verdict.PASS


def test_decide_verdict_fail_when_real_errors_remain() -> None:
    diagnostics = (
        Diagnostic(message="mismatched types", severity="error", error_code="E0308"),
    )
    assert _decide_verdict(exit_code=1, diagnostics=diagnostics, timed_out=False) == Verdict.FAIL


# -- end-to-end: real rustc with forward reference --


def test_forward_reference_filtered_at_stmt_level() -> None:
    code = """\
fn main() {
    let x = helper();
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
    assert has_errors(diagnostics)
    assert any(d.error_code == "E0425" for d in diagnostics)

    filtered = _filter_partial_noise(diagnostics)
    verdict = _decide_verdict(compile.returncode, filtered, timed_out=False)
    assert verdict == Verdict.PASS


def test_forward_reference_plus_real_error_still_fails() -> None:
    code = """\
fn main() {
    let x: i32 = "hello";
    let y = helper();
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
    assert any(d.error_code == "E0425" for d in diagnostics)
    assert any(d.error_code == "E0308" for d in diagnostics)

    filtered = _filter_partial_noise(diagnostics)
    verdict = _decide_verdict(compile.returncode, filtered, timed_out=False)
    assert verdict == Verdict.FAIL
