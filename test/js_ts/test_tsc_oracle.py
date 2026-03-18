from __future__ import annotations

from js_ts.oracles.compiler_oracle.tsc_oracle import TscOracle, TscProgramOracle
from core.types import (
    Artifact,
    ControllerState,
    Granularity,
    OracleContext,
    OracleOutput,
    RollbackScope,
    Verdict,
)
from core.types.diff_testing import TranslationSample


def _make_oracle() -> TscOracle:
    return TscOracle()


def _run_oracle(code: str) -> OracleOutput:
    oracle = _make_oracle()
    sample = TranslationSample(source_code="", source_lang="js", test_cases=[])
    artifact = Artifact(code=code, sample=sample)
    state = ControllerState(prefix=code)
    context = OracleContext()
    output = oracle.run(state, artifact, context)
    return output


# attributes


def test_oracle_attributes() -> None:
    oracle = _make_oracle()
    assert oracle.name == "tsc"
    assert oracle.required_granularity == Granularity.STMT
    assert oracle.rollback_scope == RollbackScope.STMT


# verdict


def test_pass_on_valid_code() -> None:
    output = _run_oracle("const x: number = 42;")
    assert output.verdict == Verdict.PASS
    assert output.oracle_name == "tsc"
    assert output.realized_cost == 1


def test_fail_on_type_error() -> None:
    output = _run_oracle('const x: number = "hello";')
    assert output.verdict == Verdict.FAIL
    assert any(d.error_code == "TS2322" for d in output.diagnostics)


def test_fail_on_syntax_error() -> None:
    output = _run_oracle("const x: number = ;")
    assert output.verdict == Verdict.FAIL


# noise filtering at STMT level


def test_noise_filtered_undefined_name_passes() -> None:
    output = _run_oracle("const x: number = unknownVar;")
    assert output.verdict == Verdict.PASS


def test_noise_filtered_but_real_error_still_fails() -> None:
    code = """\
const x: number = "hello";
const y = unknownVar;
"""
    output = _run_oracle(code)
    assert output.verdict == Verdict.FAIL
    assert any(d.error_code == "TS2322" for d in output.diagnostics)


# strict mode


def test_strict_implicit_any_fails() -> None:
    output = _run_oracle("function foo(x) { return x; }")
    assert output.verdict == Verdict.FAIL
    assert any(d.error_code == "TS7006" for d in output.diagnostics)


def test_strict_null_check_fails() -> None:
    code = """\
function foo(): string {
    const x: string | undefined = undefined;
    return x;
}
"""
    output = _run_oracle(code)
    assert output.verdict == Verdict.FAIL


# TscProgramOracle


def test_program_oracle_attributes() -> None:
    oracle = TscProgramOracle()
    assert oracle.name == "tsc_program"
    assert oracle.required_granularity == Granularity.PROGRAM
    assert oracle.rollback_scope == RollbackScope.PROGRAM


def test_program_oracle_noise_not_filtered() -> None:
    """At PROGRAM granularity, TS2304 (cannot find name) is a real error, not noise."""
    oracle = TscProgramOracle()
    code = "const x: number = unknownVar;"
    sample = TranslationSample(source_code="", source_lang="js", test_cases=[])
    artifact = Artifact(code=code, sample=sample)
    state = ControllerState(prefix=code)
    context = OracleContext()
    output = oracle.run(state, artifact, context)
    assert output.verdict == Verdict.FAIL
    assert any(d.error_code == "TS2304" for d in output.diagnostics)
