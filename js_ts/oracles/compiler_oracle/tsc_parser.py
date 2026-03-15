from __future__ import annotations

import re

from core.types import Diagnostic
from js_ts.oracles.compiler_oracle.tsc_driver import TscResult


_ERROR_LEVELS = {"error"}

# tsc output: filepath(line,col): severity TScode: message
_TSC_DIAG_RE = re.compile(
    r"^.+\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)$"
)

# Error codes that are expected noise when compiling partial programs.
# At sub-PROGRAM granularity the model has not finished generating all
# definitions, so "cannot find name/module" is not a real error.
_PARTIAL_COMPILATION_NOISE: frozenset[str] = frozenset({
    "TS2304",  # Cannot find name
    "TS2552",  # Cannot find name (did you mean?)
    "TS2307",  # Cannot find module
})


def parse_tsc_diagnostics(result: TscResult) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []

    for stream in (result.stdout, result.stderr):
        for line in stream.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            diag = _parse_line(stripped)
            if diag is not None:
                diagnostics.append(diag)

    if not diagnostics and result.exit_code != 0:
        raw = (result.stdout + result.stderr).strip()
        if raw:
            diagnostics.append(Diagnostic(message=raw, severity="error"))

    return tuple(diagnostics)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(diag.severity in _ERROR_LEVELS for diag in diagnostics)


def filter_partial_noise(
    diagnostics: tuple[Diagnostic, ...],
) -> tuple[Diagnostic, ...]:
    filtered = tuple(
        d for d in diagnostics
        if d.error_code not in _PARTIAL_COMPILATION_NOISE
    )
    removed_any = len(filtered) < len(diagnostics)
    if removed_any:
        has_coded_errors = any(
            d.error_code is not None and d.severity in _ERROR_LEVELS
            for d in filtered
        )
        if not has_coded_errors:
            filtered = tuple(d for d in filtered if d.severity not in _ERROR_LEVELS)
    return filtered


def _parse_line(line: str) -> Diagnostic | None:
    m = _TSC_DIAG_RE.match(line)
    if m is None:
        return None
    line_no = int(m.group(1))
    col = int(m.group(2))
    severity = m.group(3)
    error_code = m.group(4)
    message = m.group(5)
    return Diagnostic(
        message=message,
        severity=severity,
        span=(line_no, col),
        error_code=error_code,
    )
