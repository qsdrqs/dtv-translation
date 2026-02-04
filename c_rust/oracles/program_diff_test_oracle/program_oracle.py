"""Program-level differential testing oracle for C to Rust translation."""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.interfaces import Oracle
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
from core.types import Mismatch, TestCase, TranslationSample
from c_rust.oracles.program_diff_test_oracle.execution_driver import compile_and_run


class ProgramOracle(Oracle):
    """
    Program-level differential oracle.
    """

    name = "program_diff"
    required_granularity = Granularity.PROGRAM
    rollback_scope = RollbackScope.PROGRAM

    def __init__(
        self,
        compile_timeout_s: float | None = 10.0,
        run_timeout_s: float | None = 5.0,
        gcc_path: str = "gcc",
        rustc_path: str = "rustc",
    ) -> None:
        self.compile_timeout_s = compile_timeout_s
        self.run_timeout_s = run_timeout_s
        self.gcc_path = gcc_path
        self.rustc_path = rustc_path

    def run(self, state: ControllerState, artifact: Artifact, context: OracleContext) -> OracleOutput:
        """Run differential tests against the C reference."""
        _ = context
        sample = _extract_sample(artifact)
        if sample is None:
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message="No sample data in artifact"),),
                realized_cost=0,
            )

        if not sample.test_cases:
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message="No test cases in sample"),),
                realized_cost=0,
            )

        with tempfile.TemporaryDirectory(prefix="dtv-c-") as c_workdir, \
             tempfile.TemporaryDirectory(prefix="dtv-rust-") as rust_workdir:

            c_dir = Path(c_workdir)
            rust_dir = Path(rust_workdir)

            c_compile_result, c_exec_results = compile_and_run(
                source_code=sample.source_code,
                test_cases=sample.test_cases,
                language="c",
                workdir=c_dir,
                compile_timeout_s=self.compile_timeout_s,
                run_timeout_s=self.run_timeout_s,
                compiler_path=self.gcc_path,
            )

            if c_compile_result.timed_out:
                return OracleOutput(
                    oracle_name=self.name,
                    verdict=Verdict.FAIL,
                    diagnostics=(
                        Diagnostic(
                            message="C reference compilation timeout",
                            error_code="C_COMPILE_TIMEOUT",
                        ),
                    ),
                    realized_cost=1,
                )

            if c_compile_result.compilation_failed:
                return OracleOutput(
                    oracle_name=self.name,
                    verdict=Verdict.FAIL,
                    diagnostics=(
                        Diagnostic(
                            message="C reference compilation failed",
                            error_code="C_COMPILE_FAIL",
                        ),
                        Diagnostic(message=f"gcc stderr: {c_compile_result.stderr}"),
                    ),
                    realized_cost=1,
                )

            rust_compile_result, rust_exec_results = compile_and_run(
                source_code=artifact.code,
                test_cases=sample.test_cases,
                language="rust",
                workdir=rust_dir,
                compile_timeout_s=self.compile_timeout_s,
                run_timeout_s=self.run_timeout_s,
                compiler_path=self.rustc_path,
            )

            if rust_compile_result.timed_out:
                return OracleOutput(
                    oracle_name=self.name,
                    verdict=Verdict.FAIL,
                    diagnostics=(
                        Diagnostic(
                            message="Rust translation compilation timeout",
                            error_code="RUST_COMPILE_TIMEOUT",
                        ),
                    ),
                    realized_cost=1,  # Cost model: Rust compile only (C compile assumed cached).
                )

            if rust_compile_result.compilation_failed:
                return OracleOutput(
                    oracle_name=self.name,
                    verdict=Verdict.FAIL,
                    diagnostics=(
                        Diagnostic(
                            message="Rust translation compilation failed",
                            error_code="RUST_COMPILE_FAIL",
                        ),
                        Diagnostic(message=f"rustc stderr: {rust_compile_result.stderr}"),
                    ),
                    realized_cost=1,  # Cost model: Rust compile only (C compile assumed cached).
                )

            mismatches = _compare_executions(
                c_exec_results,
                rust_exec_results,
                sample.test_cases,
            )

            cost = 1 + len(sample.test_cases) * 2  # Rust compile + 2 executions per test.

            if mismatches:
                diagnostics = _mismatches_to_diagnostics(mismatches)
                return OracleOutput(
                    oracle_name=self.name,
                    verdict=Verdict.FAIL,
                    diagnostics=diagnostics,
                    realized_cost=cost,
                )

            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.PASS,
                diagnostics=(),
                realized_cost=cost,
            )


def _extract_sample(artifact: Artifact) -> TranslationSample | None:
    sample_data = artifact.sample
    if sample_data is None:
        return None

    if isinstance(sample_data, TranslationSample):
        return sample_data

    if isinstance(sample_data, dict):
        return TranslationSample(**sample_data)

    return None


def _compare_executions(
    c_results: list,
    rust_results: list,
    test_cases: list[TestCase],
) -> list[Mismatch]:
    mismatches = []

    if len(c_results) != len(rust_results) or len(c_results) != len(test_cases):
        mismatches.append(Mismatch(
            position=0,
            c_value=len(c_results),
            rust_value=len(rust_results),
            message=f"Result count mismatch: C={len(c_results)}, Rust={len(rust_results)}, tests={len(test_cases)}",
            suggested_scope=RollbackScope.PROGRAM,
        ))
        return mismatches

    for i, (c_result, rust_result, test_case) in enumerate(
        zip(c_results, rust_results, test_cases)
    ):
        test_id = test_case.test_id or f"test_{i}"

        if c_result.timed_out:
            mismatches.append(Mismatch(
                position=i,
                c_value="timeout",
                rust_value="N/A",
                message=f"{test_id}: C execution timed out",
                suggested_scope=RollbackScope.PROGRAM,
            ))
            continue

        if rust_result.timed_out:
            mismatches.append(Mismatch(
                position=i,
                c_value="N/A",
                rust_value="timeout",
                message=f"{test_id}: Rust execution timed out",
                suggested_scope=RollbackScope.PROGRAM,
            ))
            continue

        if c_result.exit_code != rust_result.exit_code:
            mismatches.append(Mismatch(
                position=i,
                c_value=c_result.exit_code,
                rust_value=rust_result.exit_code,
                message=f"{test_id}: Exit code mismatch (C={c_result.exit_code}, Rust={rust_result.exit_code})",
                suggested_scope=RollbackScope.PROGRAM,
            ))

        if c_result.stdout != rust_result.stdout:
            mismatches.append(Mismatch(
                position=i,
                c_value=c_result.stdout,
                rust_value=rust_result.stdout,
                message=f"{test_id}: stdout mismatch",
                suggested_scope=RollbackScope.PROGRAM,
            ))

        # NOTE: We do not compare stderr for now.

    return mismatches


def _mismatches_to_diagnostics(mismatches: list[Mismatch]) -> tuple[Diagnostic, ...]:
    diagnostics = []

    for mismatch in mismatches:
        diag = Diagnostic(
            message=mismatch.message,
            error_code="OUTPUT_MISMATCH",
            hint_scope=mismatch.suggested_scope,
        )
        diagnostics.append(diag)

    return tuple(diagnostics)
