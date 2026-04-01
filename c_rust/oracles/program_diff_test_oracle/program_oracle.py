"""Program-level differential testing oracle for C to Rust translation."""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.interfaces import Oracle
from core.logger import get_logger
from core.types import (
    Artifact,
    ControllerState,
    Diagnostic,
    Granularity,
    OracleContext,
    OracleOutput,
    Verdict,
)
from core.types import Mismatch, TestCase, TranslationSample
from c_rust.oracles.program_diff_test_oracle.execution_driver import compile_and_run


logger = get_logger(__name__)


class ProgramOracle(Oracle):
    """
    Program-level differential oracle.
    """

    name = "program_diff"
    required_granularity = Granularity.PROGRAM
    rollback_scope = Granularity.PROGRAM

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
        logger.info(
            "program_diff start: has_sample=%s test_cases=%s code_len=%s",
            sample is not None,
            len(sample.test_cases) if sample is not None else 0,
            len(artifact.code),
        )
        if sample is None:
            logger.info("program_diff not applicable: no sample data")
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message="No sample data in artifact"),),
                realized_cost=0,
            )

        if not sample.test_cases:
            logger.info("program_diff not applicable: no test cases")
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
                logger.info("program_diff fail: C compile timeout")
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
                logger.info("program_diff fail: C compile failed")
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
                logger.info("program_diff fail: Rust compile timeout")
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
                logger.info("program_diff fail: Rust compile failed")
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
                logger.info(
                    "program_diff fail: mismatches=%s first=%s",
                    len(mismatches),
                    mismatches[0].message,
                )
                diagnostics = _mismatches_to_diagnostics(mismatches)
                return OracleOutput(
                    oracle_name=self.name,
                    verdict=Verdict.FAIL,
                    diagnostics=diagnostics,
                    realized_cost=cost,
                )

            logger.info(
                "program_diff pass: tests=%s realized_cost=%s",
                len(sample.test_cases),
                cost,
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
            suggested_scope=Granularity.PROGRAM,
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
                suggested_scope=Granularity.PROGRAM,
            ))
            continue

        if rust_result.timed_out:
            mismatches.append(Mismatch(
                position=i,
                c_value="N/A",
                rust_value="timeout",
                message=f"{test_id}: Rust execution timed out",
                suggested_scope=Granularity.PROGRAM,
            ))
            continue

        if c_result.exit_code != rust_result.exit_code:
            stderr_note = _format_exit_code_stderr_note(
                c_stderr=c_result.stderr,
                rust_stderr=rust_result.stderr,
            )
            mismatches.append(Mismatch(
                position=i,
                c_value=c_result.exit_code,
                rust_value=rust_result.exit_code,
                message=(
                    f"{test_id}: Exit code mismatch "
                    f"(C={c_result.exit_code}, Rust={rust_result.exit_code})"
                    f"{stderr_note}"
                ),
                suggested_scope=Granularity.PROGRAM,
            ))

        if c_result.stdout != rust_result.stdout:
            mismatches.append(Mismatch(
                position=i,
                c_value=c_result.stdout,
                rust_value=rust_result.stdout,
                message=f"{test_id}: stdout mismatch",
                suggested_scope=Granularity.PROGRAM,
            ))

        # NOTE: We do not compare stderr for now.

    return mismatches


def _mismatches_to_diagnostics(mismatches: list[Mismatch]) -> tuple[Diagnostic, ...]:
    diagnostics = []

    for mismatch in mismatches:
        message = mismatch.message
        if (
            "stdout mismatch" in mismatch.message
            and isinstance(mismatch.c_value, str)
            and isinstance(mismatch.rust_value, str)
        ):
            message = _augment_stdout_mismatch_message(
                mismatch.message,
                mismatch.c_value,
                mismatch.rust_value,
            )
        diag = Diagnostic(
            message=message,
            error_code="OUTPUT_MISMATCH",
            hint_scope=mismatch.suggested_scope,
        )
        diagnostics.append(diag)

    return tuple(diagnostics)


def _first_diff_index(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"...<truncated {len(s) - max_chars} chars>"


def _augment_stdout_mismatch_message(base: str, c_stdout: str, rust_stdout: str) -> str:
    # Keep the message informative but bounded; it is used for both debugging and prompt feedback.
    max_full_chars = 400
    context_chars = 120
    max_total_chars = 1400

    c_len = len(c_stdout)
    rust_len = len(rust_stdout)
    first_diff = _first_diff_index(c_stdout, rust_stdout)

    if c_len <= max_full_chars and rust_len <= max_full_chars:
        details = (
            f"c_stdout={ascii(c_stdout)} "
            f"rust_stdout={ascii(rust_stdout)}"
        )
    else:
        start = max(0, first_diff - context_chars)
        end_c = min(c_len, first_diff + context_chars)
        end_r = min(rust_len, first_diff + context_chars)
        c_ctx = c_stdout[start:end_c]
        r_ctx = rust_stdout[start:end_r]
        details = (
            f"c_ctx@{start}:{end_c}={ascii(c_ctx)} "
            f"rust_ctx@{start}:{end_r}={ascii(r_ctx)}"
        )

    message = f"{base} (c_len={c_len}, rust_len={rust_len}, first_diff={first_diff}) {details}"
    return _truncate(message, max_total_chars)


def _format_exit_code_stderr_note(c_stderr: str, rust_stderr: str) -> str:
    c_note = _stderr_preview(c_stderr)
    rust_note = _stderr_preview(rust_stderr)
    if c_note is None and rust_note is None:
        return ""

    c_repr = "<empty>" if c_note is None else ascii(c_note)
    rust_repr = "<empty>" if rust_note is None else ascii(rust_note)
    return f" stderr(c={c_repr}, rust={rust_repr})"


def _stderr_preview(stderr: str) -> str | None:
    if not stderr:
        return None

    stripped = stderr.strip()
    if not stripped:
        return None

    first_line = stripped.splitlines()[0]
    return _truncate(first_line, 160)
