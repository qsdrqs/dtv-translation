from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

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
from c_rust.oracles.compiler_oracle.rustc_driver import RustcDriver
from c_rust.oracles.compiler_oracle.rustc_parser import has_errors, parse_rustc_diagnostics


logger = get_logger(__name__)

# Error codes that are expected noise when compiling partial programs.
# At sub-PROGRAM granularity the model has not finished generating all
# definitions, so "cannot find function/type/module" is not a real error.
# These are filtered out before verdict at STMT/BLOCK/FUNC level;
# PROGRAM-level compilation keeps them because the full program is available.
_PARTIAL_COMPILATION_NOISE: frozenset[str] = frozenset({
    "E0412",  # cannot find type in this scope
    "E0425",  # cannot find value/function in this scope
    "E0433",  # failed to resolve: use of undeclared crate or module
})


class RustcOracle(Oracle):
    name = "rustc"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def __init__(self, timeout_s: float | None = 10.0, rustc_path: str = "rustc") -> None:
        self.timeout_s = timeout_s
        self.driver = RustcDriver(rustc_path=rustc_path)

    def run(self, state: ControllerState, artifact: Artifact, context: OracleContext) -> OracleOutput:
        sample = _extract_sample(artifact)
        logger.info(
            "rustc oracle start: prefix_len=%s code_len=%s closed_function=%s",
            len(state.prefix),
            len(artifact.code),
            context.closed_function_name,
        )
        with tempfile.TemporaryDirectory(prefix="dtv-rustc-") as workdir:
            ctx = OracleContext(
                closed_stack=context.closed_stack,
                closed_function_name=context.closed_function_name,
                sample=sample,
                artifact=artifact,
                workdir=Path(workdir),
                timeout_s=self.timeout_s,
            )
            result = self.driver.compile(ctx)
            diagnostics = parse_rustc_diagnostics(result)
            logger.info(
                "rustc compile result: exit_code=%s timed_out=%s diagnostics=%s",
                result.exit_code,
                result.timed_out,
                len(diagnostics),
            )
            if result.timed_out:
                diagnostics = (Diagnostic(message="rustc_timeout", error_code="TIMEOUT"),) + diagnostics

        if self.required_granularity < Granularity.PROGRAM:
            diagnostics = _filter_partial_noise(diagnostics)

        verdict = _decide_verdict(result.exit_code, diagnostics, result.timed_out)
        first_diag = diagnostics[0].message if diagnostics else ""
        logger.info(
            "rustc oracle verdict: %s first_diagnostic=%s",
            verdict,
            first_diag,
        )
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=diagnostics,
            realized_cost=1,
        )


def _is_partial_noise(d: Diagnostic) -> bool:
    return d.error_code in _PARTIAL_COMPILATION_NOISE


def _filter_partial_noise(
    diagnostics: tuple[Diagnostic, ...],
) -> tuple[Diagnostic, ...]:
    filtered = tuple(
        d for d in diagnostics
        if not _is_partial_noise(d)
    )
    removed_any = len(filtered) < len(diagnostics)
    # Only clean up orphaned summaries ("aborting due to N previous errors")
    # when we actually removed noise.  Without this guard, real errors that
    # lack an error_code (e.g. syntax errors) would be dropped.
    if removed_any:
        has_coded_errors = any(
            d.error_code is not None and d.severity in ("error", "fatal")
            for d in filtered
        )
        if not has_coded_errors:
            filtered = tuple(d for d in filtered if d.severity not in ("error", "fatal"))
    return filtered


def _decide_verdict(exit_code: int, diagnostics: tuple, timed_out: bool) -> Verdict:
    if timed_out:
        return Verdict.FAIL
    if has_errors(diagnostics):
        return Verdict.FAIL
    # When diagnostics is empty after partial-noise filtering, exit_code may
    # still be non-zero.  Trust the (filtered) diagnostics over exit_code.
    # Guard: if no diagnostics were parsed at all AND exit failed, stay FAIL.
    if not diagnostics and exit_code != 0:
        return Verdict.FAIL
    return Verdict.PASS


class RustcProgramOracle(RustcOracle):
    name = "rustc_program"
    required_granularity = Granularity.PROGRAM
    rollback_scope = Granularity.PROGRAM


def _extract_sample(artifact: Artifact) -> Any | None:
    return artifact.sample
