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
from js_ts.oracles.compiler_oracle.tsc_driver import TscDriver
from js_ts.oracles.compiler_oracle.tsc_parser import (
    filter_partial_noise,
    filter_type_correctness,
    has_errors,
    parse_tsc_diagnostics,
)
from js_ts.oracles.diagnostic_render import render_diagnostic


logger = get_logger(__name__)


class TscOracle(Oracle):
    name = "tsc"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def __init__(self, timeout_s: float | None = 10.0, node_path: str = "node") -> None:
        self.timeout_s = timeout_s
        self.driver = TscDriver(node_path=node_path)

    def run(self, state: ControllerState, artifact: Artifact, context: OracleContext) -> OracleOutput:
        sample = artifact.sample
        logger.info(
            "tsc oracle start: prefix_len=%s code_len=%s closed_function=%s",
            len(state.prefix),
            len(artifact.code),
            context.closed_function_name,
        )
        with tempfile.TemporaryDirectory(prefix="dtv-tsc-") as workdir:
            ctx = OracleContext(
                closed_stack=context.closed_stack,
                closed_function_name=context.closed_function_name,
                sample=sample,
                artifact=artifact,
                workdir=Path(workdir),
                timeout_s=self.timeout_s,
            )
            result = self.driver.check(ctx)
            diagnostics = parse_tsc_diagnostics(result)
            logger.info(
                "tsc compile result: exit_code=%s timed_out=%s diagnostics=%s",
                result.exit_code,
                result.timed_out,
                len(diagnostics),
            )
            if result.timed_out:
                diagnostics = (Diagnostic(message="tsc_timeout", error_code="TIMEOUT"),) + diagnostics

        if self.required_granularity < Granularity.PROGRAM:
            diagnostics = filter_partial_noise(diagnostics)
        diagnostics = filter_type_correctness(diagnostics)

        rendered_diagnostics = tuple(
            render_diagnostic(d) for d in diagnostics
        )

        verdict = _decide_verdict(result.exit_code, diagnostics, result.timed_out)
        first_diag = diagnostics[0].message if diagnostics else ""
        logger.info(
            "tsc oracle verdict: %s first_diagnostic=%s",
            verdict,
            first_diag,
        )
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=diagnostics,
            rendered_diagnostics=rendered_diagnostics,
            realized_cost=1,
        )


class TscProgramOracle(TscOracle):
    name = "tsc_program"
    required_granularity = Granularity.PROGRAM
    rollback_scope = Granularity.PROGRAM


def _decide_verdict(exit_code: int, diagnostics: tuple[Diagnostic, ...], timed_out: bool) -> Verdict:
    if timed_out:
        return Verdict.FAIL
    if has_errors(diagnostics):
        return Verdict.FAIL
    # Unlike c_rust, tsc does not emit "failure-note" summary messages, so
    # after noise filtering diagnostics can be legitimately empty while
    # exit_code is non-zero.  The parser already creates a fallback
    # Diagnostic from raw output when it cannot extract structured
    # diagnostics, so empty-after-filtering means all errors were noise.
    return Verdict.PASS
