from __future__ import annotations

import json
from typing import Any

from core.types import Diagnostic, DiagnosticSpan
from js_ts.oracles.compiler_oracle.tsc_driver import TscResult


_ERROR_LEVELS = {"error"}

_PARTIAL_COMPILATION_NOISE: frozenset[str] = frozenset({
    "TS2304",
    "TS2552",
    "TS2307",
    "TS2564",
})

_TYPE_CORRECTNESS_BLOCKLIST: frozenset[str] = frozenset({
    "TS2322",
    "TS2339",
    "TS2345",
})


def parse_tsc_diagnostics(result: TscResult) -> tuple[Diagnostic, ...]:
    try:
        entries = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        if result.exit_code != 0:
            raw = (result.stdout + result.stderr).strip()
            if raw:
                return (Diagnostic(message=raw, severity="error"),)
        return ()

    if not isinstance(entries, list):
        return ()

    diagnostics: list[Diagnostic] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        diag = _parse_entry(entry)
        if diag is not None:
            diagnostics.append(diag)
    return tuple(diagnostics)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(diag.severity in _ERROR_LEVELS for diag in diagnostics)


def filter_type_correctness(
    diagnostics: tuple[Diagnostic, ...],
) -> tuple[Diagnostic, ...]:
    return tuple(
        d for d in diagnostics
        if not (
            d.error_code is not None
            and d.error_code in _TYPE_CORRECTNESS_BLOCKLIST
            and d.severity in _ERROR_LEVELS
        )
    )


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


def _parse_entry(entry: dict[str, Any]) -> Diagnostic | None:
    message = entry.get("message")
    if not isinstance(message, str) or not message:
        return None

    severity = entry.get("severity", "error")
    error_code = entry.get("code")
    if isinstance(error_code, int):
        error_code = f"TS{error_code}"
    elif not isinstance(error_code, str):
        error_code = None

    spans: list[DiagnosticSpan] = []
    line = entry.get("line")
    col = entry.get("col")
    if isinstance(line, int):
        spans.append(DiagnosticSpan(
            line=line,
            col=col if isinstance(col, int) else 0,
            is_primary=True,
        ))

    related = entry.get("relatedInformation")
    if isinstance(related, list):
        for ri in related:
            if not isinstance(ri, dict):
                continue
            ri_line = ri.get("line")
            if not isinstance(ri_line, int):
                continue
            ri_col = ri.get("col")
            ri_message = ri.get("message", "")
            spans.append(DiagnosticSpan(
                line=ri_line,
                col=ri_col if isinstance(ri_col, int) else 0,
                message=ri_message if isinstance(ri_message, str) else "",
            ))

    return Diagnostic(
        message=message,
        severity=severity if isinstance(severity, str) else "error",
        spans=tuple(spans),
        error_code=error_code,
    )
