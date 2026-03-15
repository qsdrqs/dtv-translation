from __future__ import annotations

from pathlib import Path

from js_ts.oracles.compiler_oracle.tsc_driver import TscResult
from js_ts.oracles.compiler_oracle.tsc_oracle import _decide_verdict
from js_ts.oracles.compiler_oracle.tsc_parser import (
    filter_partial_noise,
    has_errors,
    parse_tsc_diagnostics,
)
from core.types import Diagnostic, Verdict
from test.js_ts.utils import check_typescript


def _tsc_result_from_check(code: str) -> TscResult:
    check = check_typescript(code)
    return TscResult(
        stdout=check.stdout,
        stderr=check.stderr,
        exit_code=check.returncode,
        elapsed_ms=0,
        command=("tsc",),
        source_path=Path("check.ts"),
        timed_out=False,
    )


# parse_tsc_diagnostics


def test_parse_type_mismatch() -> None:
    result = _tsc_result_from_check('const x: number = "hello";')
    diagnostics = parse_tsc_diagnostics(result)
    assert has_errors(diagnostics)
    assert len(diagnostics) == 1
    assert diagnostics[0].error_code == "TS2322"
    assert "not assignable" in diagnostics[0].message
    assert diagnostics[0].severity == "error"


def test_parse_undefined_name() -> None:
    result = _tsc_result_from_check("const x: number = unknownVar;")
    diagnostics = parse_tsc_diagnostics(result)
    assert has_errors(diagnostics)
    assert any(d.error_code == "TS2304" for d in diagnostics)


def test_parse_multiple_errors() -> None:
    code = """\
const x: number = "hello";
const y: string = 42;
const z = unknownVar;
"""
    result = _tsc_result_from_check(code)
    diagnostics = parse_tsc_diagnostics(result)
    assert has_errors(diagnostics)
    codes = tuple(d.error_code for d in diagnostics)
    assert "TS2322" in codes
    assert "TS2304" in codes


def test_parse_clean_code() -> None:
    result = _tsc_result_from_check("const x: number = 42;")
    diagnostics = parse_tsc_diagnostics(result)
    assert not has_errors(diagnostics)
    assert diagnostics == ()


def test_parse_span_is_line_col() -> None:
    result = _tsc_result_from_check('const x: number = "hello";')
    diagnostics = parse_tsc_diagnostics(result)
    assert len(diagnostics) == 1
    assert diagnostics[0].span == (1, 7)


# filter_partial_noise


def test_filter_removes_ts2304_and_orphaned_summary() -> None:
    diagnostics = (
        Diagnostic(message="Cannot find name 'foo'", error_code="TS2304"),
        Diagnostic(message="Cannot find name 'bar'", error_code="TS2304"),
    )
    filtered = filter_partial_noise(diagnostics)
    assert filtered == ()


def test_filter_removes_ts2552_and_ts2307() -> None:
    diagnostics = (
        Diagnostic(message="Cannot find name 'foo'. Did you mean 'bar'?", error_code="TS2552"),
        Diagnostic(message="Cannot find module 'x'", error_code="TS2307"),
    )
    filtered = filter_partial_noise(diagnostics)
    assert filtered == ()


def test_filter_keeps_real_errors() -> None:
    diagnostics = (
        Diagnostic(message="Cannot find name 'foo'", error_code="TS2304"),
        Diagnostic(message="Type 'string' is not assignable to type 'number'.", error_code="TS2322"),
    )
    filtered = filter_partial_noise(diagnostics)
    assert filtered == (
        Diagnostic(message="Type 'string' is not assignable to type 'number'.", error_code="TS2322"),
    )


def test_filter_keeps_warnings() -> None:
    diagnostics = (
        Diagnostic(message="unused variable", severity="warning", error_code="TS6133"),
    )
    filtered = filter_partial_noise(diagnostics)
    assert filtered == diagnostics


# _decide_verdict


def test_decide_verdict_pass_clean() -> None:
    assert _decide_verdict(exit_code=0, diagnostics=(), timed_out=False) == Verdict.PASS


def test_decide_verdict_fail_with_errors() -> None:
    diagnostics = (
        Diagnostic(message="type mismatch", severity="error", error_code="TS2322"),
    )
    assert _decide_verdict(exit_code=2, diagnostics=diagnostics, timed_out=False) == Verdict.FAIL


def test_decide_verdict_fail_on_timeout() -> None:
    assert _decide_verdict(exit_code=124, diagnostics=(), timed_out=True) == Verdict.FAIL


def test_decide_verdict_pass_nonzero_after_noise_filtered() -> None:
    # Empty diagnostics + non-zero exit means all errors were noise - PASS.
    # The parser creates a fallback Diagnostic for truly-unparseable output,
    # so this state only occurs after filter_partial_noise removed everything.
    assert _decide_verdict(exit_code=2, diagnostics=(), timed_out=False) == Verdict.PASS


def test_decide_verdict_pass_when_only_warnings() -> None:
    diagnostics = (
        Diagnostic(message="unused variable", severity="warning"),
    )
    assert _decide_verdict(exit_code=0, diagnostics=diagnostics, timed_out=False) == Verdict.PASS


# end-to-end: real tsc with forward reference


def test_forward_reference_filtered_at_stmt_level() -> None:
    code = """\
const x: number = unknownVar;
"""
    result = _tsc_result_from_check(code)
    diagnostics = parse_tsc_diagnostics(result)
    assert has_errors(diagnostics)
    assert any(d.error_code == "TS2304" for d in diagnostics)

    filtered = filter_partial_noise(diagnostics)
    verdict = _decide_verdict(result.exit_code, filtered, timed_out=False)
    assert verdict == Verdict.PASS


def test_forward_reference_plus_real_error_still_fails() -> None:
    code = """\
const x: number = "hello";
const y = unknownVar;
"""
    result = _tsc_result_from_check(code)
    diagnostics = parse_tsc_diagnostics(result)
    assert any(d.error_code == "TS2304" for d in diagnostics)
    assert any(d.error_code == "TS2322" for d in diagnostics)

    filtered = filter_partial_noise(diagnostics)
    verdict = _decide_verdict(result.exit_code, filtered, timed_out=False)
    assert verdict == Verdict.FAIL
