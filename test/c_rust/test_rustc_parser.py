from __future__ import annotations

from pathlib import Path

from c_rust.oracles.compiler_oracle.compiler_oracle import (
    RustcProgramOracle,
    _decide_verdict,
    _filter_partial_noise,
    _filter_resolvable_trait_bounds,
)
from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult
from c_rust.oracles.compiler_oracle.rustc_parser import has_errors, parse_rustc_diagnostics
from core.types import Diagnostic, DiagnosticSpan, Verdict
from test.c_rust.utils import compile_rust


def test_rustc_parser_extracts_code_span() -> None:
    code = """\
fn foo() -> i32 {
    "hi"
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
    assert tuple(diag.message for diag in diagnostics) == (
        "mismatched types",
        "aborting due to 1 previous error",
        "For more information about this error, try `rustc --explain E0308`.",
    )
    assert tuple(diag.error_code for diag in diagnostics) == ("E0308", None, None)
    assert tuple(diag.severity for diag in diagnostics) == ("error", "error", "failure-note")

    diag = diagnostics[0]
    primary = next((s for s in diag.spans if s.is_primary), None)
    assert primary is not None
    assert primary.line == 2  # "hi" is on line 2


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


# RustcProgramOracle


def test_filter_partial_noise_removes_e0425_for_functions() -> None:
    diagnostics = (
        Diagnostic(
            message="cannot find function `helper` in this scope",
            error_code="E0425",
        ),
        Diagnostic(message="aborting due to 1 previous error", error_code=None),
    )
    filtered = _filter_partial_noise(diagnostics)
    assert filtered == ()


def test_program_oracle_attributes() -> None:
    from core.types import Granularity
    oracle = RustcProgramOracle()
    assert oracle.name == "rustc_program"
    assert oracle.required_granularity == Granularity.PROGRAM
    assert oracle.rollback_scope == Granularity.PROGRAM


def test_program_oracle_noise_not_filtered() -> None:
    """At PROGRAM granularity, E0425 (cannot find value) is a real error, not noise."""
    from core.types import (
        Artifact,
        ControllerState,
        Granularity,
        OracleContext,
        Verdict,
    )
    from core.types.diff_testing import TranslationSample

    code = """\
fn main() {
    let x = helper();
}
"""
    oracle = RustcProgramOracle()
    sample = TranslationSample(source_code="", source_lang="c", test_cases=[])
    artifact = Artifact(code=code, sample=sample)
    state = ControllerState(prefix=code)
    context = OracleContext()
    output = oracle.run(state, artifact, context)
    assert output.verdict == Verdict.FAIL
    assert any(d.error_code == "E0425" for d in output.diagnostics)


# -- _filter_resolvable_trait_bounds tests --


def _e0277_diag(
    *,
    primary_text: str = "",
    suggestion: str | None = None,
) -> Diagnostic:
    primary = DiagnosticSpan(line=1, col=1, is_primary=True, text=primary_text)
    spans: tuple[DiagnosticSpan, ...] = (primary,)
    if suggestion is not None:
        spans = spans + (DiagnosticSpan(line=2, col=1, suggested_replacement=suggestion),)
    return Diagnostic(
        message="can't compare `Foo` with `Foo`",
        severity="error",
        error_code="E0277",
        spans=spans,
    )


def test_filter_resolvable_trait_bounds_removes_e0277_with_suggestion() -> None:
    diagnostics = (
        _e0277_diag(primary_text="let v: Vec<Foo> = vec![]; v.sort();", suggestion="#[derive(Ord)]\n"),
    )
    assert _filter_resolvable_trait_bounds(diagnostics) == ()


def test_filter_resolvable_trait_bounds_removes_e0277_at_impl_header() -> None:
    diagnostics = (
        _e0277_diag(primary_text="impl Bar for S {}", suggestion=None),
    )
    assert _filter_resolvable_trait_bounds(diagnostics) == ()


def test_filter_resolvable_trait_bounds_keeps_e0277_without_signals() -> None:
    diagnostics = (
        _e0277_diag(primary_text="fn main() { show(Foo); }", suggestion=None),
    )
    assert _filter_resolvable_trait_bounds(diagnostics) == diagnostics


def test_filter_resolvable_trait_bounds_removes_e0277_with_non_derive_suggestion() -> None:
    diagnostics = (
        _e0277_diag(
            primary_text="    let v: Vec<Option<Box<Foo>>> = vec![None; 4];",
            suggestion="&",
        ),
    )
    assert _filter_resolvable_trait_bounds(diagnostics) == ()


def test_filter_resolvable_trait_bounds_keeps_non_e0277() -> None:
    diagnostics = (
        Diagnostic(
            message="mismatched types",
            severity="error",
            error_code="E0308",
            spans=(DiagnosticSpan(line=1, col=1, is_primary=True, text="impl X for Y {"),),
        ),
    )
    assert _filter_resolvable_trait_bounds(diagnostics) == diagnostics


def test_filter_resolvable_trait_bounds_removes_orphaned_summary() -> None:
    diagnostics = (
        _e0277_diag(primary_text="impl Ord for Team {", suggestion="#[derive(PartialOrd)]\n"),
        Diagnostic(message="aborting due to 1 previous error", error_code=None, severity="error"),
    )
    assert _filter_resolvable_trait_bounds(diagnostics) == ()


# -- parser captures new fields --


def test_rustc_parser_captures_span_text_and_suggested_replacement() -> None:
    code = """\
#[derive(PartialEq, Eq)]
struct Foo { v: i32 }

impl Ord for Foo {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.v.cmp(&other.v)
    }
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
    e0277 = next((d for d in diagnostics if d.error_code == "E0277"), None)
    assert e0277 is not None
    primary = next((s for s in e0277.spans if s.is_primary), None)
    assert primary is not None
    assert primary.text.lstrip().startswith("impl Ord for Foo")
    assert any(
        s.suggested_replacement and "derive" in s.suggested_replacement
        for s in e0277.spans
    )


# -- e2e: real rustc output, filter + verdict --


def test_e2e_derivable_super_trait_filtered_at_stmt_level() -> None:
    code = """\
#[derive(PartialEq, Eq)]
struct Foo { v: i32 }

impl Ord for Foo {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.v.cmp(&other.v)
    }
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
    assert any(d.error_code == "E0277" for d in diagnostics)
    filtered = _filter_partial_noise(diagnostics)
    filtered = _filter_resolvable_trait_bounds(filtered)
    verdict = _decide_verdict(compile.returncode, filtered, timed_out=False)
    assert verdict == Verdict.PASS


def test_e2e_non_derivable_super_trait_filtered_at_stmt_level() -> None:
    code = """\
trait Foo { fn foo(&self); }
trait Bar: Foo {}

struct S;

impl Bar for S {}
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
    assert any(d.error_code == "E0277" for d in diagnostics)
    filtered = _filter_partial_noise(diagnostics)
    filtered = _filter_resolvable_trait_bounds(filtered)
    verdict = _decide_verdict(compile.returncode, filtered, timed_out=False)
    assert verdict == Verdict.PASS


def test_e2e_non_derive_suggestion_filtered_at_stmt_level() -> None:
    code = """\
struct Foo;

fn main() {
    let v: Vec<Option<Box<Foo>>> = vec![None; 4];
}
"""
    compile = compile_rust(code, crate_type="bin", error_format="json")
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
    assert any(d.error_code == "E0277" for d in diagnostics)
    filtered = _filter_partial_noise(diagnostics)
    filtered = _filter_resolvable_trait_bounds(filtered)
    verdict = _decide_verdict(compile.returncode, filtered, timed_out=False)
    assert verdict == Verdict.PASS


def test_e2e_display_missing_not_filtered_at_stmt_level() -> None:
    code = """\
use std::fmt::Display;

struct Foo;

fn show<T: Display>(x: T) { println!("{}", x); }

fn main() { show(Foo); }
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
    assert any(d.error_code == "E0277" for d in diagnostics)
    filtered = _filter_partial_noise(diagnostics)
    filtered = _filter_resolvable_trait_bounds(filtered)
    verdict = _decide_verdict(compile.returncode, filtered, timed_out=False)
    assert verdict == Verdict.FAIL
