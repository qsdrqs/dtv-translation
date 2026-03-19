from __future__ import annotations

import shutil
import subprocess

import pytest

from core.types import (
    Artifact,
    ControllerState,
    Diagnostic,
    Granularity,
    OracleContext,
    OracleOutput,
    RollbackScope,
    Verdict,
)
from core.types.diff_testing import TranslationSample
from js_ts.oracles.eslint_oracle.eslint_driver import EslintDriver
from js_ts.oracles.eslint_oracle.eslint_oracle import EslintOracle
from js_ts.oracles.eslint_oracle.eslint_parser import parse_eslint_messages


UNTYPED_CODE = "function foo(x) { return x; }\n"
TYPED_CODE = "function foo(x: number): number { return x; }\nconst y: number = 1;\n"


def _require_eslint() -> None:
    eslint = shutil.which("eslint")
    npx = shutil.which("npx")
    if eslint is None and npx is None:
        pytest.skip("eslint not available")
    command = [eslint, "--version"] if eslint is not None else [npx, "eslint", "--version"]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("eslint not functional")


def _make_oracle() -> EslintOracle:
    _require_eslint()
    return EslintOracle()


def _run_oracle(code: str) -> OracleOutput:
    oracle = _make_oracle()
    sample = TranslationSample(source_code="", source_lang="js", test_cases=[])
    artifact = Artifact(code=code, sample=sample)
    state = ControllerState(prefix=code)
    context = OracleContext()
    return oracle.run(state, artifact, context)


def test_driver_returns_violations_on_untyped_code() -> None:
    _require_eslint()
    driver = EslintDriver()
    result = driver.check(UNTYPED_CODE)
    assert result.error_count > 0
    assert any(message["ruleId"] == "@typescript-eslint/typedef" for message in result.messages)


def test_driver_returns_clean_on_typed_code() -> None:
    _require_eslint()
    driver = EslintDriver()
    result = driver.check(TYPED_CODE)
    assert result.error_count == 0
    assert result.messages == []


def test_parser_converts_to_diagnostics() -> None:
    diagnostics = parse_eslint_messages([
        {
            "ruleId": "@typescript-eslint/typedef",
            "severity": 2,
            "message": "Expected x to have a type annotation.",
            "line": 1,
            "column": 14,
        }
    ])
    assert diagnostics == (
        Diagnostic(
            message="[@typescript-eslint/typedef] Expected x to have a type annotation.",
            severity="error",
            span=(1, 14),
            error_code="@typescript-eslint/typedef",
        ),
    )


def test_parser_extracts_rule_id_as_error_code() -> None:
    diagnostics = parse_eslint_messages([
        {
            "ruleId": "@typescript-eslint/explicit-function-return-type",
            "severity": 2,
            "message": "Missing return type on function.",
            "line": 1,
            "column": 1,
        }
    ])
    assert diagnostics[0].error_code == "@typescript-eslint/explicit-function-return-type"


def test_parser_extracts_line_col_as_span() -> None:
    diagnostics = parse_eslint_messages([
        {
            "ruleId": "@typescript-eslint/typedef",
            "severity": 1,
            "message": "Expected value to have a type annotation.",
            "line": 3,
            "column": 7,
        }
    ])
    assert diagnostics[0].span == (3, 7)
    assert diagnostics[0].severity == "warning"


def test_oracle_fail_on_missing_annotations() -> None:
    output = _run_oracle(UNTYPED_CODE)
    assert output.verdict == Verdict.FAIL
    assert output.oracle_name == "eslint"
    assert any(d.error_code == "@typescript-eslint/typedef" for d in output.diagnostics)


def test_oracle_pass_on_typed_code() -> None:
    output = _run_oracle(TYPED_CODE)
    assert output.verdict == Verdict.PASS
    assert output.oracle_name == "eslint"
    assert output.realized_cost == 1


def test_oracle_attributes() -> None:
    oracle = _make_oracle()
    assert oracle.name == "eslint"
    assert oracle.required_granularity == Granularity.STMT
    assert oracle.rollback_scope == RollbackScope.STMT
