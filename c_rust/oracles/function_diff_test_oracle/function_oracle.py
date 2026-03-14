"""Function-level differential testing oracle for C to Rust translation."""

from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from core.interfaces import Oracle
from core.logger import get_logger
from core.toolchain import env_with_pinned_rustup_toolchain
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
from c_rust.oracles.function_diff_test_oracle.c_instrumenter import (
    FunctionSignature,
    find_c_function_info,
    instrument_c_functions,
    list_c_function_names,
)
from c_rust.oracles.function_diff_test_oracle.extern_c_bridge import generate_extern_c_wrapper
from c_rust.oracles.function_diff_test_oracle.ffi_bridge import (
    build_normalized_lookup,
    find_missing_functions,
    generate_ffi_bridge,
    normalize_identifier,
)
from c_rust.oracles.function_diff_test_oracle.rust_instrumenter import (
    RustSignature,
    extract_function_signature as extract_rust_signature,
    instrument_rust_functions,
    list_rust_function_names,
)
from core.trace_comparator import (
    TraceComparisonStats,
    filter_trace_for_function,
    find_first_mismatch,
    parse_trace_events,
    remap_trace_function_id,
)
from core.types import ExecutionResult, TranslationSample
from c_rust.oracles.program_diff_test_oracle.execution_driver import run_binary


logger = get_logger(__name__)


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
        requested_name = context.closed_function_name
        logger.info(
            "function_diff start: requested_function=%s closed_stack=%s has_sample=%s test_cases=%s",
            requested_name,
            len(context.closed_stack),
            sample is not None,
            len(sample.test_cases) if sample is not None else 0,
        )
        validation = _validate_sample(sample, requested_name, self.name)
        if validation is not None:
            logger.info(
                "function_diff early return: verdict=%s reason=%s",
                validation.verdict,
                _first_diagnostic_message(validation),
            )
            return validation
        assert sample is not None
        assert requested_name is not None

        c_candidates = list_c_function_names(sample.source_code)
        c_function_name, c_reason = _resolve_function_name(requested_name, c_candidates, "C")
        if c_function_name is None:
            logger.info(
                "function_diff not applicable: requested=%s c_candidates=%s reason=%s",
                requested_name,
                len(c_candidates),
                c_reason,
            )
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message=c_reason or "C function not found"),),
                realized_cost=0,
            )

        rust_candidates = list_rust_function_names(artifact.code)
        rust_function_name, rust_reason = _resolve_function_name(requested_name, rust_candidates, "Rust")
        if rust_function_name is None:
            logger.info(
                "function_diff not applicable: requested=%s rust_candidates=%s reason=%s",
                requested_name,
                len(rust_candidates),
                rust_reason,
            )
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message=rust_reason or "Rust function not found"),),
                realized_cost=0,
            )

        c_info = find_c_function_info(sample.source_code, c_function_name)
        if c_info is None or c_info.signature is None:
            logger.info(
                "function_diff not applicable: C signature missing for function=%s",
                c_function_name,
            )
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message="C signature not found"),),
                realized_cost=0,
            )
        if c_info.is_static:
            logger.info(
                "function_diff not applicable: C function is static (%s)",
                c_function_name,
            )
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message="C function is static"),),
                realized_cost=0,
            )

        rust_sig = extract_rust_signature(artifact.code, rust_function_name)
        if rust_sig is None:
            logger.info(
                "function_diff not applicable: Rust signature missing for function=%s",
                rust_function_name,
            )
            return OracleOutput(
                oracle_name=self.name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message="Rust signature not found"),),
                realized_cost=0,
            )

        prepared, prepare_err = _prepare_sources(
            artifact,
            sample,
            c_function_name,
            rust_function_name,
            self.name,
            c_info.signature,
            rust_sig,
        )
        if prepare_err is not None:
            logger.info(
                "function_diff preparation return: verdict=%s reason=%s",
                prepare_err.verdict,
                _first_diagnostic_message(prepare_err),
            )
            return prepare_err
        assert prepared is not None

        with tempfile.TemporaryDirectory(prefix="dtv-c-") as c_workdir, \
             tempfile.TemporaryDirectory(prefix="dtv-rust-") as rust_workdir:

            c_dir = Path(c_workdir)
            rust_dir = Path(rust_workdir)

            compiled, compile_err = _compile_binaries(
                prepared,
                c_dir,
                rust_dir,
                gcc_path=self.gcc_path,
                rustc_path=self.rustc_path,
                timeout_s=self.compile_timeout_s,
                oracle_name=self.name,
                function_name=c_function_name,
            )
            if compile_err is not None:
                logger.info(
                    "function_diff compile return: verdict=%s reason=%s",
                    compile_err.verdict,
                    _first_diagnostic_message(compile_err),
                )
                return compile_err
            assert compiled is not None

            c_binary, cdylib_path = compiled
            output = _run_tests_and_compare(
                oracle_name=self.name,
                sample=sample,
                c_function_name=c_function_name,
                rust_function_name=rust_function_name,
                c_binary=c_binary,
                cdylib_path=cdylib_path,
                run_timeout_s=self.run_timeout_s,
            )
            logger.info(
                "function_diff finish: verdict=%s diagnostics=%s first=%s cost=%s",
                output.verdict,
                len(output.diagnostics),
                _first_diagnostic_message(output),
                output.realized_cost,
            )
            return output


def _first_diagnostic_message(output: OracleOutput) -> str:
    if not output.diagnostics:
        return ""
    return output.diagnostics[0].message


@dataclass(frozen=True)
class PreparedSources:
    c_source: str
    rust_source: str


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


def _resolve_function_name(
    requested_name: str,
    candidates: list[str],
    label: str,
) -> tuple[str | None, str | None]:
    if not candidates:
        return None, f"No {label} functions found"
    if requested_name in candidates:
        return requested_name, None
    lookup = build_normalized_lookup(candidates)
    normalized = normalize_identifier(requested_name)
    matches = lookup.get(normalized)
    if not matches:
        return None, f"{label} function not found: {requested_name}"
    if len(matches) != 1:
        return None, f"{label} function name ambiguous for {requested_name}"
    return matches[0], None


def _prepare_sources(
    artifact: Artifact,
    sample: TranslationSample,
    c_function_name: str,
    rust_function_name: str,
    oracle_name: str,
    c_signature: FunctionSignature,
    rust_signature: RustSignature,
) -> tuple[PreparedSources | None, OracleOutput | None]:
    instrumented_c = instrument_c_functions(sample.source_code, target_function=c_function_name)
    instrumented_rust = instrument_rust_functions(artifact.code, target_function=rust_function_name)

    wrapper_result = generate_extern_c_wrapper(
        c_function_name,
        rust_function_name,
        c_signature,
        rust_signature,
    )
    if wrapper_result.code is None:
        return None, OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.NOT_APPLICABLE,
            diagnostics=(Diagnostic(message=wrapper_result.reason or "extern wrapper not applicable"),),
            realized_cost=0,
        )

    # FFI discovery uses the original sources to avoid trace wrappers skewing call/def detection.
    missing = find_missing_functions(artifact.code, sample.source_code)
    if missing.missing is None:
        return None, OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.NOT_APPLICABLE,
            diagnostics=(Diagnostic(message=missing.reason or "FFI not applicable"),),
            realized_cost=0,
        )

    bridge_code = ""
    if missing.missing:
        bridge = generate_ffi_bridge(artifact.code, sample.source_code)
        if bridge.code is None:
            return None, OracleOutput(
                oracle_name=oracle_name,
                verdict=Verdict.NOT_APPLICABLE,
                diagnostics=(Diagnostic(message=bridge.reason or "FFI not applicable"),),
                realized_cost=0,
            )
        bridge_code = bridge.code

    if bridge_code:
        instrumented_rust = f"{instrumented_rust}\n\n{bridge_code}\n"

    instrumented_rust = f"{instrumented_rust}\n\n{wrapper_result.code}\n"

    return PreparedSources(
        c_source=instrumented_c,
        rust_source=instrumented_rust,
    ), None


def _compile_binaries(
    prepared: PreparedSources,
    c_dir: Path,
    rust_dir: Path,
    gcc_path: str,
    rustc_path: str,
    timeout_s: float | None,
    oracle_name: str,
    function_name: str,
) -> tuple[tuple[Path, Path] | None, OracleOutput | None]:
    """Compile C executable (baseline) and Rust cdylib (LD_PRELOAD override).

    Returns (c_binary_path, cdylib_path) on success.
    """
    c_compile_result = _compile_c_binary(
        prepared.c_source,
        c_dir,
        gcc_path=gcc_path,
        timeout_s=timeout_s,
    )
    if c_compile_result.timed_out:
        return None, OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="C compilation timeout", error_code="C_COMPILE_TIMEOUT"),),
            realized_cost=1,
        )
    if c_compile_result.compilation_failed:
        return None, OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="C compilation failed", error_code="C_COMPILE_FAIL"),
                Diagnostic(message=f"gcc stderr: {c_compile_result.stderr}"),
            ),
            realized_cost=1,
        )

    cdylib_compile_result, cdylib_path = _compile_cdylib(
        prepared.rust_source,
        rust_dir,
        rustc_path=rustc_path,
        timeout_s=timeout_s,
        function_name=function_name,
    )
    if cdylib_compile_result.timed_out:
        return None, OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="Rust cdylib compilation timeout", error_code="RUST_CDYLIB_TIMEOUT"),),
            realized_cost=1,
        )
    if cdylib_compile_result.compilation_failed:
        return None, OracleOutput(
            oracle_name=oracle_name,
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="Rust cdylib compilation failed", error_code="RUST_CDYLIB_FAIL"),
                Diagnostic(message=f"rustc stderr: {cdylib_compile_result.stderr}"),
            ),
            realized_cost=1,
        )

    return (c_dir / "program", cdylib_path), None


def _run_tests_and_compare(
    oracle_name: str,
    sample: TranslationSample,
    c_function_name: str,
    rust_function_name: str,
    c_binary: Path,
    cdylib_path: Path,
    run_timeout_s: float | None,
) -> OracleOutput:
    cost = 1
    coverage = TraceComparisonStats()
    for i, test_case in enumerate(sample.test_cases):
        test_id = test_case.test_id or f"test_{i}"

        # Baseline: native C function.  LD_PRELOAD run: Rust cdylib overrides target symbol.
        c_exec = run_binary(c_binary, test_case, timeout_s=run_timeout_s)
        rust_exec = run_binary(c_binary, test_case, timeout_s=run_timeout_s, ld_preload=cdylib_path)
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
        c_trace = filter_trace_for_function(
            parse_trace_events(c_exec.stderr),
            c_function_name,
        )
        rust_events = parse_trace_events(rust_exec.stderr)
        # Instrumented Rust emits trace events under the Rust function name,
        # while the extern "C" wrapper exports under the C name.  When the
        # two names differ (e.g. calculateSum vs calculate_sum), the first
        # filter by c_function_name will be empty and the fallback by
        # rust_function_name is the actual match.  When names are identical
        # the first filter succeeds directly.
        rust_trace = filter_trace_for_function(rust_events, c_function_name)
        if not rust_trace:
            rust_trace = filter_trace_for_function(rust_events, rust_function_name)
            if rust_trace and rust_function_name != c_function_name:
                rust_trace = remap_trace_function_id(rust_trace, c_function_name)
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
        # Export symbols so LD_PRELOAD cdylib can resolve C helpers (e.g. clamp_value).
        "-rdynamic",
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


def _compile_cdylib(
    source_code: str,
    workdir: Path,
    rustc_path: str,
    timeout_s: float | None,
    link_objects: tuple[Path, ...] = (),
    function_name: str = "lib",
) -> tuple[ExecutionResult, Path]:
    """Compile Rust source as a cdylib shared library for LD_PRELOAD injection."""
    source_file = workdir / "program.rs"
    lib_file = workdir / f"lib{function_name}.so"
    source_file.write_text(source_code, encoding="utf-8")

    cmd = [
        rustc_path,
        str(source_file),
        "--crate-type=cdylib",
        "--edition=2021",
        "-o",
        str(lib_file),
    ]
    cmd.extend(str(path) for path in link_objects)
    return _run_compile(cmd, workdir, timeout_s), lib_file


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
            env=env_with_pinned_rustup_toolchain(),
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



