from __future__ import annotations

import shutil
import subprocess

import pytest

from core.types import (
    Artifact,
    ControllerState,
    Diagnostic,
    DiagnosticSpan,
    Granularity,
    OracleContext,
    OracleOutput,
    RenderStatus,
    RollbackScope,
    Verdict,
)
from core.types.diff_testing import TranslationSample
from js_ts.oracles.eslint_oracle.eslint_driver import EslintDriver
from js_ts.oracles.eslint_oracle.eslint_oracle import EslintOracle
from js_ts.oracles.eslint_oracle.eslint_parser import (
    filter_post_prefix_diagnostics,
    parse_eslint_messages,
)
from js_ts.render import JSToTSRenderer


UNTYPED_CODE = "function foo(x) { return x; }\n"
TYPED_CODE = "function foo(x: number): number { return x; }\nconst y: number = 1;\n"
MODEL_PREFIX_BEFORE_RENDERER_CLOSING = """\
import * as readline from 'readline';

function trap(height: number[]): number {
  const n = height.length;
"""


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


def _run_oracle(code: str, prefix: str | None = None) -> OracleOutput:
    oracle = _make_oracle()
    sample = TranslationSample(source_code="", source_lang="js", test_cases=[])
    artifact = Artifact(code=code, sample=sample)
    state = ControllerState(prefix=code if prefix is None else prefix)
    context = OracleContext()
    return oracle.run(state, artifact, context)


def _render_prefix(prefix: str) -> Artifact:
    renderer = JSToTSRenderer()
    result = renderer.try_render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    return result.artifact


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
            message="Expected x to have a type annotation.",
            severity="error",
            spans=(DiagnosticSpan(line=1, col=14, is_primary=True),),
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
    primary = next(s for s in diagnostics[0].spans if s.is_primary)
    assert (primary.line, primary.col) == (3, 7)
    assert diagnostics[0].severity == "warning"


def test_filter_post_prefix_diagnostics_drops_renderer_only_diagnostic() -> None:
    diagnostics = parse_eslint_messages([
        {
            "ruleId": "@typescript-eslint/no-explicit-any",
            "severity": 2,
            "message": "Unexpected any. Specify a different type.",
            "line": 5,
            "column": 23,
        }
    ])
    filtered = filter_post_prefix_diagnostics(diagnostics, MODEL_PREFIX_BEFORE_RENDERER_CLOSING)
    assert filtered == ()


def test_filter_post_prefix_diagnostics_keeps_diagnostic_inside_prefix() -> None:
    diagnostics = parse_eslint_messages([
        {
            "ruleId": "@typescript-eslint/typedef",
            "severity": 2,
            "message": "Expected n to have a type annotation.",
            "line": 4,
            "column": 9,
        }
    ])
    filtered = filter_post_prefix_diagnostics(diagnostics, MODEL_PREFIX_BEFORE_RENDERER_CLOSING)
    assert filtered == diagnostics


def test_filter_post_prefix_diagnostics_keeps_prefix_error_and_drops_renderer_noise() -> None:
    diagnostics = parse_eslint_messages([
        {
            "ruleId": "@typescript-eslint/typedef",
            "severity": 2,
            "message": "Expected n to have a type annotation.",
            "line": 4,
            "column": 9,
        },
        {
            "ruleId": "@typescript-eslint/no-explicit-any",
            "severity": 2,
            "message": "Unexpected any. Specify a different type.",
            "line": 5,
            "column": 23,
        },
    ])
    filtered = filter_post_prefix_diagnostics(diagnostics, MODEL_PREFIX_BEFORE_RENDERER_CLOSING)
    assert filtered == (
        Diagnostic(
            message="Expected n to have a type annotation.",
            severity="error",
            spans=(DiagnosticSpan(line=4, col=9, is_primary=True),),
            error_code="@typescript-eslint/typedef",
        ),
    )


def test_oracle_ignores_renderer_closing_diagnostic_beyond_prefix() -> None:
    prefix = """\
function sumPair(): number {
  const total: number = 1;
"""
    artifact = _render_prefix(prefix)

    assert "return undefined as any;" in artifact.code

    output = _run_oracle(artifact.code, prefix=prefix)

    assert output.verdict == Verdict.PASS
    assert all(d.error_code != "@typescript-eslint/no-explicit-any" for d in output.diagnostics)


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
