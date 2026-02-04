"""Function-level differential testing oracle for C to Rust translation."""

from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
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
from c_rust.oracles.function_diff_test_oracle.c_instrumenter import instrument_c_functions
from c_rust.oracles.function_diff_test_oracle.ffi_bridge import find_missing_functions, generate_ffi_bridge
from c_rust.oracles.function_diff_test_oracle.rust_instrumenter import instrument_rust_functions
from c_rust.oracles.function_diff_test_oracle.trace_comparator import (
    TraceComparisonStats,
    find_first_mismatch,
    parse_trace_events,
)
from core.types import ExecutionResult, ExecutionTraceEvent, TraceEventKind, TranslationSample
from c_rust.oracles.program_diff_test_oracle.execution_driver import run_binary


class FunctionOracle(Oracle):
    """
    Function-level differential oracle with trace-based comparison.
    """

    name = "function_diff"
    required_granularity = Granularity.FUNC
    rollback_scope = RollbackScope.FUNC

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
        """Run differential tests against the C reference with trace comparison."""
        sample = _extract_sample(artifact)
        function_name = context.closed_function_name
        validation = _validate_sample(sample, function_name, self.name)
        if validation is not None:
            return validation
        assert sample is not None
        assert function_name is not None

        prepared = _prepare_sources(artifact, sample, function_name, self.name)
        if isinstance(prepared, OracleOutput):
            return prepared

        with tempfile.TemporaryDirectory(prefix="dtv-c-") as c_workdir, \
             tempfile.TemporaryDirectory(prefix="dtv-rust-") as rust_workdir:

            c_dir = Path(c_workdir)
            rust_dir = Path(rust_workdir)

            compiled = _compile_binaries(
                prepared,
                c_dir,
                rust_dir,
                gcc_path=self.gcc_path,
                rustc_path=self.rustc_path,
                timeout_s=self.compile_timeout_s,
                oracle_name=self.name,
            )
            if isinstance(compiled, OracleOutput):
                return compiled

            c_binary, rust_binary = compiled
            return _run_tests_and_compare(
                oracle_name=self.name,
                sample=sample,
                function_name=function_name,
                c_binary=c_binary,
                rust_binary=rust_binary,
                run_timeout_s=self.run_timeout_s,
            )


@dataclass(frozen=True)
class PreparedSources:
    c_source: str
    rust_source: str
    needs_ffi: bool


def _extract_sample(artifact: Artifact) -> TranslationSample | None:
    sample_data = artifact.sample
    if sample_data is None:
        return None
    if isinstance(sample_data, TranslationSample):
        return sample_data
    if isinstance(sample_data, dict):
        return TranslationSample(**sample_data)
    return None


def _validate_sample(
    sample: TranslationSample | None,
    function_name: str | None,
    oracle_name: str,
) -> OracleOutput | None:
    if sample is None:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.NOT_APPLICABLE,
            diagnostics=(Diagnostic(message="No sample data in artifact"),),
            realized_cost=0,
        )

    if not sample.test_cases:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.NOT_APPLICABLE,
            diagnostics=(Diagnostic(message="No test cases in sample"),),
            realized_cost=0,
        )

    if not function_name:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.NOT_APPLICABLE,
            diagnostics=(Diagnostic(message="No closed function in context"),),
            realized_cost=0,
        )

    return None


def _prepare_sources(
    artifact: Artifact,
    sample: TranslationSample,
    function_name: str,
    oracle_name: str,
) -> PreparedSources | OracleOutput:
    instrumented_c = instrument_c_functions(sample.source_code, target_function=function_name)
    instrumented_rust = instrument_rust_functions(artifact.code, target_function=function_name)

    # FFI discovery uses the original sources to avoid trace wrappers skewing call/def detection.
    missing = find_missing_functions(artifact.code, sample.source_code)
    if missing.missing is None:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.NOT_APPLICABLE,
            diagnostics=(Diagnostic(message=missing.reason or "FFI not applicable"),),
            realized_cost=0,
        )

    bridge_code = ""
    if missing.missing:
        bridge = generate_ffi_bridge(artifact.code, sample.source_code)
        if bridge.code is None:
            return OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message=bridge.reason or "FFI not applicable"),),
                realized_cost=0,
            )
        bridge_code = bridge.code

    if bridge_code:
        instrumented_rust = f"{instrumented_rust}\n\n{bridge_code}\n"

    return PreparedSources(
        c_source=instrumented_c,
        rust_source=instrumented_rust,
        needs_ffi=bool(missing.missing),
    )


def _compile_binaries(
    prepared: PreparedSources,
    c_dir: Path,
    rust_dir: Path,
    gcc_path: str,
    rustc_path: str,
    timeout_s: float | None,
    oracle_name: str,
) -> tuple[Path, Path] | OracleOutput:
    c_compile_result = _compile_c_binary(
        prepared.c_source,
        c_dir,
        gcc_path=gcc_path,
        timeout_s=timeout_s,
    )
    if c_compile_result.timed_out:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="C compilation timeout", error_code="C_COMPILE_TIMEOUT"),),
            realized_cost=1,
        )
    if c_compile_result.compilation_failed:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="C compilation failed", error_code="C_COMPILE_FAIL"),
                Diagnostic(message=f"gcc stderr: {c_compile_result.stderr}"),
            ),
            realized_cost=1,
        )

    c_object_path = None
    if prepared.needs_ffi:
        # Only build a C object when Rust needs to link missing C symbols.
        c_object_result, c_object_path = _compile_c_object(
            prepared.c_source,
            c_dir,
            gcc_path=gcc_path,
            timeout_s=timeout_s,
        )
        if c_object_result.timed_out:
            return OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.FAIL,
                diagnostics=(Diagnostic(message="C object compilation timeout", error_code="C_OBJECT_TIMEOUT"),),
                realized_cost=1,
            )
        if c_object_result.compilation_failed:
            return OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.FAIL,
                diagnostics=(
                    Diagnostic(message="C object compilation failed", error_code="C_OBJECT_FAIL"),
                    Diagnostic(message=f"gcc stderr: {c_object_result.stderr}"),
                ),
                realized_cost=1,
            )

    rust_compile_result = _compile_rust_binary(
        prepared.rust_source,
        rust_dir,
        rustc_path=rustc_path,
        timeout_s=timeout_s,
        link_objects=(c_object_path,) if c_object_path else (),
    )
    if rust_compile_result.timed_out:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="Rust compilation timeout", error_code="RUST_COMPILE_TIMEOUT"),),
            realized_cost=1,
        )
    if rust_compile_result.compilation_failed:
        return OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="Rust compilation failed", error_code="RUST_COMPILE_FAIL"),
                Diagnostic(message=f"rustc stderr: {rust_compile_result.stderr}"),
            ),
            realized_cost=1,
        )

    return c_dir / "program", rust_dir / "program"


def _run_tests_and_compare(
    oracle_name: str,
    sample: TranslationSample,
    function_name: str,
    c_binary: Path,
    rust_binary: Path,
    run_timeout_s: float | None,
) -> OracleOutput:
    cost = 1
    coverage = TraceComparisonStats()
    for i, test_case in enumerate(sample.test_cases):
        test_id = test_case.test_id or f"test_{i}"

        # Two binaries: instrumented C for the baseline, instrumented Rust for translation.
        c_exec = run_binary(c_binary, test_case, timeout_s=run_timeout_s)
        rust_exec = run_binary(rust_binary, test_case, timeout_s=run_timeout_s)
        cost += 2

        if c_exec.timed_out:
            return OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.FAIL,
                diagnostics=(Diagnostic(message=f"{test_id}: C execution timed out", error_code="C_RUN_TIMEOUT"),),
                realized_cost=cost,
            )
        if rust_exec.timed_out:
            return OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.FAIL,
                diagnostics=(Diagnostic(message=f"{test_id}: Rust execution timed out", error_code="RUST_RUN_TIMEOUT"),),
                realized_cost=cost,
            )
        if c_exec.exit_code != rust_exec.exit_code:
            return OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.FAIL,
                diagnostics=(Diagnostic(
                    message=(
                        f"{test_id}: Exit code mismatch "
                        f"(C={c_exec.exit_code}, Rust={rust_exec.exit_code})"
                    ),
                    error_code="EXIT_CODE_MISMATCH",
                    hint_scope=RollbackScope.FUNC,
                ),),
                realized_cost=cost,
            )

        # Function oracle compares only the target function's enter/exit events.
        c_trace = _filter_trace_for_function(
            parse_trace_events(c_exec.stderr),
            function_name,
        )
        rust_trace = _filter_trace_for_function(
            parse_trace_events(rust_exec.stderr),
            function_name,
        )
        mismatch, stats = find_first_mismatch(
            c_trace,
            rust_trace,
            scope=RollbackScope.FUNC,
        )
        coverage.add(stats)
        if mismatch:
            return OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.FAIL,
                diagnostics=(
                    Diagnostic(
                        message=f"{test_id}: {mismatch.message}",
                        error_code="TRACE_MISMATCH",
                        hint_scope=mismatch.suggested_scope or RollbackScope.FUNC,
                    ),
                    _coverage_diagnostic(coverage),
                ),
                realized_cost=cost,
            )

    return OracleOutput(
        oracle_name=oracle_name,
        verdict=Verdict.PASS,
        diagnostics=(_coverage_diagnostic(coverage),),
        realized_cost=cost,
    )


def _coverage_diagnostic(stats: TraceComparisonStats) -> Diagnostic:
    message = (
        "comparison_coverage: "
        f"compared={stats.compared_fields}, "
        f"skipped={stats.skipped_fields}, "
        f"total={stats.total_fields}"
    )
    return Diagnostic(message=message, severity="info")


def _compile_c_binary(
    source_code: str,
    workdir: Path,
    gcc_path: str,
    timeout_s: float | None,
) -> ExecutionResult:
    source_file = workdir / "program.c"
    binary_file = workdir / "program"
    source_file.write_text(source_code, encoding="utf-8")

    cmd = [
        gcc_path,
        "-o",
        str(binary_file),
        str(source_file),
        "-std=c11",
        "-Wall",
    ]
    return _run_compile(cmd, workdir, timeout_s)


def _compile_c_object(
    source_code: str,
    workdir: Path,
    gcc_path: str,
    timeout_s: float | None,
) -> tuple[ExecutionResult, Path]:
    source_file = workdir / "program.c"
    object_file = workdir / "program.o"
    source_file.write_text(source_code, encoding="utf-8")

    cmd = [
        gcc_path,
        "-c",
        str(source_file),
        "-o",
        str(object_file),
        "-std=c11",
        "-Wall",
    ]
    return _run_compile(cmd, workdir, timeout_s), object_file


def _compile_rust_binary(
    source_code: str,
    workdir: Path,
    rustc_path: str,
    timeout_s: float | None,
    link_objects: tuple[Path, ...] = (),
) -> ExecutionResult:
    source_file = workdir / "program.rs"
    binary_file = workdir / "program"
    source_file.write_text(source_code, encoding="utf-8")

    cmd = [
        rustc_path,
        str(source_file),
        "-o",
        str(binary_file),
        "--edition=2021",
    ]
    cmd.extend(str(path) for path in link_objects)
    return _run_compile(cmd, workdir, timeout_s)


def _run_compile(
    cmd: list[str],
    workdir: Path,
    timeout_s: float | None,
) -> ExecutionResult:
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_s,
            cwd=workdir,
            check=False,
            text=True,
        )
        elapsed_ms = (time.time() - start_time) * 1000
        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
            elapsed_ms=elapsed_ms,
            compilation_failed=result.returncode != 0,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = (time.time() - start_time) * 1000
        return ExecutionResult(
            exit_code=None,
            stdout=exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "",
            stderr=exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "",
            timed_out=True,
            elapsed_ms=elapsed_ms,
            compilation_failed=True,
        )


def _filter_trace_for_function(
    events: list[ExecutionTraceEvent],
    function_name: str,
) -> list[ExecutionTraceEvent]:
    return [
        event
        for event in events
        if event.kind in (TraceEventKind.FUNC_ENTER, TraceEventKind.FUNC_EXIT)
        and event.id == function_name
    ]
