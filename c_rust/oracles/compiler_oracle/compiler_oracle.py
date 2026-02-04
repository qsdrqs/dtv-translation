from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

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
from c_rust.oracles.compiler_oracle.rustc_driver import RustcDriver
from c_rust.oracles.compiler_oracle.rustc_parser import has_errors, parse_rustc_diagnostics


class RustcOracle(Oracle):
    name = "rustc"
    required_granularity = Granularity.STMT
    rollback_scope = RollbackScope.STMT

    def __init__(self, timeout_s: float | None = 10.0, rustc_path: str = "rustc") -> None:
        self.timeout_s = timeout_s
        self.driver = RustcDriver(rustc_path=rustc_path)

    def run(self, state: ControllerState, artifact: Artifact, context: OracleContext) -> OracleOutput:
        sample = _extract_sample(artifact)
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
            if result.timed_out:
                diagnostics = (Diagnostic(message="rustc_timeout", error_code="TIMEOUT"),) + diagnostics

        verdict = _decide_verdict(result.exit_code, diagnostics, result.timed_out)
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=diagnostics,
            realized_cost=1,
        )


def _decide_verdict(exit_code: int, diagnostics: tuple, timed_out: bool) -> Verdict:
    if timed_out:
        return Verdict.FAIL
    if exit_code == 0 and not has_errors(diagnostics):
        return Verdict.PASS
    return Verdict.FAIL


def _extract_sample(artifact: Artifact) -> Any | None:
    return artifact.sample
