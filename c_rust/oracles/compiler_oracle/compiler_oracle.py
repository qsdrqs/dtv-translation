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

_IMPL_HEADER_PREFIXES: tuple[str, ...] = ("impl ", "impl<")


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
            pairs = parse_rustc_diagnostics(result)
            logger.info(
                "rustc compile result: exit_code=%s timed_out=%s diagnostics=%s",
                result.exit_code,
                result.timed_out,
                len(pairs),
            )
            if result.timed_out:
                timeout_pair = (Diagnostic(message="rustc_timeout", error_code="TIMEOUT"), "rustc_timeout")
                pairs = (timeout_pair,) + pairs

        if self.required_granularity < Granularity.PROGRAM:
            pairs = _filter_pairs(pairs, _is_partial_noise)
            pairs = _filter_pairs(pairs, _is_resolvable_trait_bound)

        diagnostics = tuple(d for d, _ in pairs)
        rendered_diagnostics = tuple(r for _, r in pairs)

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
            rendered_diagnostics=rendered_diagnostics,
            realized_cost=1,
        )


def _is_partial_noise(d: Diagnostic) -> bool:
    return d.error_code in _PARTIAL_COMPILATION_NOISE


def _filter_pairs(
    pairs: tuple[tuple[Diagnostic, str], ...],
    drop_predicate,
) -> tuple[tuple[Diagnostic, str], ...]:
    """Filter (diag, rendered) pairs by a Diagnostic-only predicate.

    Drops pairs where `drop_predicate(diag)` is true, then strips orphaned
    error-summary diagnostics (those that lack error_code) when the resulting
    set has no coded errors left. Mirrors the previous Diagnostic-only
    filters' guard against dropping real syntax errors that have no code.
    """
    kept = tuple(p for p in pairs if not drop_predicate(p[0]))
    if len(kept) == len(pairs):
        return kept
    has_coded_errors = any(
        d.error_code is not None and d.severity in ("error", "fatal")
        for d, _ in kept
    )
    if has_coded_errors:
        return kept
    return tuple(p for p in kept if p[0].severity not in ("error", "fatal"))


def _filter_partial_noise(
    diagnostics: tuple[Diagnostic, ...],
) -> tuple[Diagnostic, ...]:
    """Diagnostic-only adapter over `_filter_pairs` for tests + external callers."""
    pairs = tuple((d, "") for d in diagnostics)
    return tuple(d for d, _ in _filter_pairs(pairs, _is_partial_noise))


def _filter_resolvable_trait_bounds(
    diagnostics: tuple[Diagnostic, ...],
) -> tuple[Diagnostic, ...]:
    """Diagnostic-only adapter over `_filter_pairs` for tests + external callers."""
    pairs = tuple((d, "") for d in diagnostics)
    return tuple(d for d, _ in _filter_pairs(pairs, _is_resolvable_trait_bound))


def _is_impl_header(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith(_IMPL_HEADER_PREFIXES):
        return False
    return " for " in stripped and "{" in stripped


def _is_resolvable_trait_bound(d: Diagnostic) -> bool:
    # Filter E0277 whose fix may land in later stmts: rustc attached any machine
    # suggestion (derive, borrow, deref - all count as "rustc knows a local
    # auto-fix"), or the error is at `impl X for Y {` (a later super-trait
    # impl satisfies it). Strict post-hoc recheck catches any never-fixed cases.
    if d.error_code != "E0277":
        return False
    if any(s.suggested_replacement for s in d.spans):
        return True
    primary = next((s for s in d.spans if s.is_primary), None)
    return primary is not None and _is_impl_header(primary.text)


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
