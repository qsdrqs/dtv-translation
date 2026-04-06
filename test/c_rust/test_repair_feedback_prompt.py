from __future__ import annotations

from pathlib import Path

import pytest

from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult
from c_rust.oracles.compiler_oracle.rustc_parser import has_errors, parse_rustc_diagnostics
from core.types import Diagnostic, DiagnosticSpan, OracleOutput, Granularity, Verdict
from feedback.formatter import RepairFeedbackFormatConfig, build_repair_feedback
from feedback.feedback import FeedbackState
from test.c_rust.utils import compile_rust


_ERROR_LEVELS = {"error", "fatal"}


def _compile_diagnostics(code: str):
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
    return parse_rustc_diagnostics(result)


def _compile_oracle_output(code: str) -> OracleOutput:
    diagnostics = _compile_diagnostics(code)
    verdict = Verdict.FAIL if has_errors(diagnostics) else Verdict.PASS
    return OracleOutput(
        oracle_name="rustc",
        verdict=verdict,
        diagnostics=diagnostics,
        rollback_scope=Granularity.STMT,
    )


def _error_messages(diagnostics) -> list[str]:
    return [
        diag.message
        for diag in diagnostics
        if diag.severity.lower().strip() in _ERROR_LEVELS
    ]


def _prefixed_error_messages(oracle_name: str, diagnostics) -> list[str]:
    return [f"[{oracle_name}] {message}" for message in _error_messages(diagnostics)]


def _first_hint(diagnostics) -> str | None:
    for diag in diagnostics:
        for hint in diag.hints:
            text = hint.strip()
            if text:
                return text
    return None


def test_feedback_state_filters_warnings_and_keeps_current_errors() -> None:
    warning_output = _compile_oracle_output(
        """\
fn main() {
    let mut x = 1;
    println!("{}", x);
}
"""
    )
    assert warning_output.verdict == Verdict.PASS

    error_output = _compile_oracle_output(
        """\
fn main() {
    let x = 1;
    let _y = &mut x;
}
"""
    )
    assert error_output.verdict == Verdict.FAIL
    assert _error_messages(error_output.diagnostics)

    feedback_state = FeedbackState()

    feedback_state.on_verify([warning_output])
    assert feedback_state.encode() == ""
    assert feedback_state.best_fix_hint() is None

    feedback_state.on_verify([error_output])
    assert feedback_state.encode().splitlines() == _prefixed_error_messages(
        "rustc", error_output.diagnostics
    )
    expected_hint = _first_hint(error_output.diagnostics)
    if expected_hint is None:
        pytest.skip("rustc did not emit a help hint on this toolchain")
    assert feedback_state.best_fix_hint() == expected_hint

    feedback_state.on_verify([warning_output])
    assert feedback_state.encode() == ""
    assert feedback_state.best_fix_hint() is None


def test_build_repair_feedback_uses_real_rustc_hint() -> None:
    diagnostics = _compile_diagnostics(
        """\
fn main() {
    let x = 1;
    let _y = &mut x;
}
"""
    )
    expected_hint = _first_hint(diagnostics)
    if expected_hint is None:
        pytest.skip("rustc did not emit a help hint on this toolchain")
    assert expected_hint is not None
    feedback_state = FeedbackState()
    feedback_state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=diagnostics,
            rollback_scope=Granularity.STMT,
        )
    ])

    prompt = build_repair_feedback(feedback_state, "")
    diagnostic_blocks: list[str] = []
    for output in feedback_state.recent_outputs:
        for diag in output.diagnostics:
            header = [f"oracle={output.oracle_name}", f"severity={diag.severity}"]
            if diag.error_code is not None:
                header.append(f"code={diag.error_code}")
            if diag.hint_scope is not None:
                header.append(f"hint_scope={diag.hint_scope.value}")
            primary = next((s for s in diag.spans if s.is_primary), None)
            if primary is not None:
                header.append(f"span={primary.line}:{primary.col}")
            hints = tuple(hint.strip() for hint in diag.hints if hint.strip())
            hints_block = ""
            if hints:
                hints_block = f"""
hints:
{"\n".join(f"  - {hint}" for hint in hints)}"""
            diagnostic_blocks.append(
                f"""- {' '.join(header)}
message: {diag.message}{hints_block}"""
            )
    expected = f"""/* repair feedback:
failed snippet:
(empty)

diagnostics:
{"\n".join(diagnostic_blocks)}
*/"""
    assert prompt == expected


def test_build_repair_feedback_handles_missing_hint_from_real_rustc() -> None:
    diagnostics = _compile_diagnostics(
        """\
fn main() {
    let x: i32 = "1";
}
"""
    )
    if any(diag.hints for diag in diagnostics):
        pytest.skip("rustc emitted a help hint on this toolchain; fallback path not applicable")
    feedback_state = FeedbackState()
    feedback_state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=diagnostics,
            rollback_scope=Granularity.STMT,
        )
    ])

    prompt = build_repair_feedback(feedback_state, "")
    diagnostic_blocks: list[str] = []
    for output in feedback_state.recent_outputs:
        for diag in output.diagnostics:
            header = [f"oracle={output.oracle_name}", f"severity={diag.severity}"]
            if diag.error_code is not None:
                header.append(f"code={diag.error_code}")
            if diag.hint_scope is not None:
                header.append(f"hint_scope={diag.hint_scope.value}")
            primary = next((s for s in diag.spans if s.is_primary), None)
            if primary is not None:
                header.append(f"span={primary.line}:{primary.col}")
            hints = tuple(hint.strip() for hint in diag.hints if hint.strip())
            hints_block = ""
            if hints:
                hints_block = f"""
hints:
{"\n".join(f"  - {hint}" for hint in hints)}"""
            diagnostic_blocks.append(
                f"""- {' '.join(header)}
message: {diag.message}{hints_block}"""
            )
    expected = f"""/* repair feedback:
failed snippet:
(empty)

diagnostics:
{"\n".join(diagnostic_blocks)}
*/"""
    assert prompt == expected


def test_feedback_scope_aligned_selection_filters_by_scope() -> None:
    from core.types import Granularity

    stmt_diagnostics = _compile_diagnostics(
        """\
fn main() {
    let x = 1;
    let _y = &mut x;
}
"""
    )
    assert has_errors(stmt_diagnostics)
    stmt_output = OracleOutput(
        oracle_name="rustc",
        verdict=Verdict.FAIL,
        diagnostics=stmt_diagnostics,
        rollback_scope=Granularity.STMT,
    )

    func_diagnostics = _compile_diagnostics(
        """\
fn foo() -> i32 {
    "hi"
}
"""
    )
    assert has_errors(func_diagnostics)
    func_output = OracleOutput(
        oracle_name="func_oracle",
        verdict=Verdict.FAIL,
        diagnostics=func_diagnostics,
        rollback_scope=Granularity.FUNC,
    )

    feedback_state = FeedbackState()
    feedback_state.on_verify([stmt_output, func_output], selected_scope=Granularity.STMT)

    encoded = feedback_state.encode()
    assert encoded.splitlines() == _prefixed_error_messages("rustc", stmt_diagnostics)


def test_feedback_scope_aligned_includes_all_same_scope_oracles() -> None:
    from core.types import Granularity

    stmt_diag_1 = _compile_diagnostics(
        """\
fn main() {
    let x = 1;
    let _y = &mut x;
}
"""
    )
    stmt_output_1 = OracleOutput(
        oracle_name="oracle_a",
        verdict=Verdict.FAIL,
        diagnostics=stmt_diag_1,
        rollback_scope=Granularity.STMT,
    )

    stmt_diag_2 = _compile_diagnostics(
        """\
fn main() {
    let x: i32 = "1";
}
"""
    )
    stmt_output_2 = OracleOutput(
        oracle_name="oracle_b",
        verdict=Verdict.FAIL,
        diagnostics=stmt_diag_2,
        rollback_scope=Granularity.STMT,
    )

    feedback_state = FeedbackState()
    feedback_state.on_verify([stmt_output_1, stmt_output_2], selected_scope=Granularity.STMT)

    encoded = feedback_state.encode()
    assert encoded.splitlines() == (
        _prefixed_error_messages("oracle_a", stmt_diag_1)
        + _prefixed_error_messages("oracle_b", stmt_diag_2)
    )


def test_feedback_raises_when_fail_has_no_error_fatal_diagnostics() -> None:
    warning_only = (
        Diagnostic(
            message="unused variable: `x`",
            severity="warning",
        ),
    )
    fail_output = OracleOutput(
        oracle_name="rustc",
        verdict=Verdict.FAIL,
        diagnostics=warning_only,
        rollback_scope=Granularity.STMT,
    )

    feedback_state = FeedbackState()
    with pytest.raises(ValueError, match="FAIL output has no error/fatal diagnostics"):
        feedback_state.on_verify([fail_output], selected_scope=Granularity.STMT)


def test_feedback_ignores_fail_outputs_outside_selected_scope() -> None:
    func_diagnostics = _compile_diagnostics(
        """\
fn foo() -> i32 {
    "hi"
}
"""
    )
    func_output = OracleOutput(
        oracle_name="func_oracle",
        verdict=Verdict.FAIL,
        diagnostics=func_diagnostics,
        rollback_scope=Granularity.FUNC,
    )

    feedback_state = FeedbackState()
    feedback_state.on_verify([func_output], selected_scope=Granularity.STMT)
    assert feedback_state.encode() == ""


def test_feedback_hint_from_scope_aligned_diagnostics_only() -> None:
    stmt_diagnostics = _compile_diagnostics(
        """\
fn main() {
    let x = 1;
    let _y = &mut x;
}
"""
    )
    stmt_output = OracleOutput(
        oracle_name="rustc",
        verdict=Verdict.FAIL,
        diagnostics=stmt_diagnostics,
        rollback_scope=Granularity.STMT,
    )

    func_diagnostics = _compile_diagnostics(
        """\
fn foo() -> i32 {
    if true { 1 }
}
"""
    )
    func_output = OracleOutput(
        oracle_name="func_oracle",
        verdict=Verdict.FAIL,
        diagnostics=func_diagnostics,
        rollback_scope=Granularity.FUNC,
    )

    feedback_state = FeedbackState()
    feedback_state.on_verify([stmt_output, func_output], selected_scope=Granularity.STMT)

    hint = feedback_state.best_fix_hint()
    expected_hint = _first_hint(stmt_diagnostics)
    if expected_hint is None:
        pytest.skip("rustc did not emit a help hint on this toolchain")
    assert expected_hint is not None
    assert hint == expected_hint


def test_build_repair_feedback_full_format_with_scope_aligned_diagnostics() -> None:
    stmt_diagnostics = _compile_diagnostics(
        """\
fn main() {
    let x = 1;
    let _y = &mut x;
}
"""
    )
    stmt_output = OracleOutput(
        oracle_name="rustc",
        verdict=Verdict.FAIL,
        diagnostics=stmt_diagnostics,
        rollback_scope=Granularity.STMT,
    )

    feedback_state = FeedbackState()
    feedback_state.on_verify([stmt_output], selected_scope=Granularity.STMT)

    prompt = build_repair_feedback(feedback_state, "")
    diagnostic_blocks: list[str] = []
    for output in feedback_state.recent_outputs:
        for diag in output.diagnostics:
            header = [f"oracle={output.oracle_name}", f"severity={diag.severity}"]
            if diag.error_code is not None:
                header.append(f"code={diag.error_code}")
            if diag.hint_scope is not None:
                header.append(f"hint_scope={diag.hint_scope.value}")
            primary = next((s for s in diag.spans if s.is_primary), None)
            if primary is not None:
                header.append(f"span={primary.line}:{primary.col}")
            hints = tuple(hint.strip() for hint in diag.hints if hint.strip())
            hints_block = ""
            if hints:
                hints_block = f"""
hints:
{"\n".join(f"  - {hint}" for hint in hints)}"""
            diagnostic_blocks.append(
                f"""- {' '.join(header)}
message: {diag.message}{hints_block}"""
            )
    expected = f"""/* repair feedback:
failed snippet:
(empty)

diagnostics:
{"\n".join(diagnostic_blocks)}
*/"""
    assert prompt == expected


def test_build_repair_feedback_uses_existing_diagnostic_fields() -> None:
    fail_output = OracleOutput(
        oracle_name="function_diff",
        verdict=Verdict.FAIL,
        diagnostics=(
            Diagnostic(
                message="test_2: Exit code mismatch (C=0, Rust=1)",
                severity="error",
                spans=(DiagnosticSpan(line=10, col=20, is_primary=True),),
                error_code="EXIT_CODE_MISMATCH",
                hint_scope=Granularity.FUNC,
                hints=("check return value handling",),
            ),
        ),
        rollback_scope=Granularity.FUNC,
    )
    feedback_state = FeedbackState()
    feedback_state.on_verify([fail_output], selected_scope=Granularity.FUNC)
    prompt = build_repair_feedback(feedback_state, "let result = buggy_call();")
    assert prompt == """/* repair feedback:
failed snippet:
let result = buggy_call();

diagnostics:
- oracle=function_diff severity=error code=EXIT_CODE_MISMATCH hint_scope=func span=10:20
message: test_2: Exit code mismatch (C=0, Rust=1)
hints:
  - check return value handling
*/"""


def test_build_repair_feedback_can_omit_failed_snippet() -> None:
    fail_output = OracleOutput(
        oracle_name="function_diff",
        verdict=Verdict.FAIL,
        diagnostics=(
            Diagnostic(
                message="test failure",
                severity="error",
            ),
        ),
        rollback_scope=Granularity.FUNC,
    )
    feedback_state = FeedbackState()
    feedback_state.on_verify([fail_output], selected_scope=Granularity.FUNC)
    prompt = build_repair_feedback(
        feedback_state,
        "let result = buggy_call();",
        RepairFeedbackFormatConfig(include_failed_snippet=False),
    )
    assert prompt == """/* repair feedback:
diagnostics:
- oracle=function_diff severity=error
message: test failure
*/"""


def test_build_repair_feedback_preserves_snippet_indentation() -> None:
    fail_output = OracleOutput(
        oracle_name="function_diff",
        verdict=Verdict.FAIL,
        diagnostics=(
            Diagnostic(
                message="test failure",
                severity="error",
            ),
        ),
        rollback_scope=Granularity.STMT,
    )
    feedback_state = FeedbackState()
    feedback_state.on_verify([fail_output], selected_scope=Granularity.STMT)

    prompt = build_repair_feedback(
        feedback_state,
        "    let result = buggy_call();\n    return result;\n",
    )

    assert prompt == """    /* repair feedback:
    failed snippet:
    let result = buggy_call();
    return result;

    diagnostics:
    - oracle=function_diff severity=error
    message: test failure
    */"""


def test_build_repair_feedback_preserves_relative_nested_indentation() -> None:
    fail_output = OracleOutput(
        oracle_name="function_diff",
        verdict=Verdict.FAIL,
        diagnostics=(
            Diagnostic(
                message="test failure",
                severity="error",
            ),
        ),
        rollback_scope=Granularity.STMT,
    )
    feedback_state = FeedbackState()
    feedback_state.on_verify([fail_output], selected_scope=Granularity.STMT)

    prompt = build_repair_feedback(
        feedback_state,
        "    if cond {\n        return buggy_call();\n    }\n",
    )

    assert prompt == """    /* repair feedback:
    failed snippet:
    if cond {
        return buggy_call();
    }

    diagnostics:
    - oracle=function_diff severity=error
    message: test failure
    */"""


def test_build_repair_feedback_uses_shared_indent_for_uneven_lines() -> None:
    fail_output = OracleOutput(
        oracle_name="function_diff",
        verdict=Verdict.FAIL,
        diagnostics=(
            Diagnostic(
                message="test failure",
                severity="error",
            ),
        ),
        rollback_scope=Granularity.STMT,
    )
    feedback_state = FeedbackState()
    feedback_state.on_verify([fail_output], selected_scope=Granularity.STMT)

    prompt = build_repair_feedback(
        feedback_state,
        "    expr1();\n  expr2();\n",
    )

    assert prompt == """    /* repair feedback:
    failed snippet:
      expr1();
    expr2();

    diagnostics:
    - oracle=function_diff severity=error
    message: test failure
    */"""


def test_feedback_preserves_deterministic_oracle_and_diagnostic_order() -> None:
    from core.types import Diagnostic, Granularity

    oracle_a_diagnostics = (
        Diagnostic(message="error from oracle_a diagnostic 1", severity="error"),
        Diagnostic(message="error from oracle_a diagnostic 2", severity="error"),
    )
    oracle_a = OracleOutput(
        oracle_name="oracle_a",
        verdict=Verdict.FAIL,
        diagnostics=oracle_a_diagnostics,
        rollback_scope=Granularity.STMT,
    )

    oracle_b_diagnostics = (
        Diagnostic(message="error from oracle_b diagnostic 1", severity="error"),
        Diagnostic(message="error from oracle_b diagnostic 2", severity="error"),
    )
    oracle_b = OracleOutput(
        oracle_name="oracle_b",
        verdict=Verdict.FAIL,
        diagnostics=oracle_b_diagnostics,
        rollback_scope=Granularity.STMT,
    )

    feedback_state = FeedbackState()
    feedback_state.on_verify([oracle_a, oracle_b], selected_scope=Granularity.STMT)

    encoded = feedback_state.encode()
    lines = encoded.strip().split("\n")
    assert lines == [
        "[oracle_a] error from oracle_a diagnostic 1",
        "[oracle_a] error from oracle_a diagnostic 2",
        "[oracle_b] error from oracle_b diagnostic 1",
        "[oracle_b] error from oracle_b diagnostic 2",
    ]
