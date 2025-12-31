from __future__ import annotations

import json
from typing import Any

from core.types import Diagnostic
from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult


_ERROR_LEVELS = {"error", "fatal"}
_NON_DIAGNOSTIC_JSON = object()


def parse_rustc_diagnostics(result: RustcResult) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    fallback_lines: list[str] = []

    for stream in (result.stderr, result.stdout):
        for line in stream.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            diagnostic = _parse_json_line(stripped)
            if diagnostic is _NON_DIAGNOSTIC_JSON:
                continue
            if diagnostic is not None and isinstance(diagnostic, Diagnostic):
                diagnostics.append(diagnostic)
            else:
                fallback_lines.append(stripped)

    if not diagnostics and fallback_lines:
        severity = "error" if result.exit_code != 0 else "warning"
        diagnostics.append(Diagnostic(message=fallback_lines[0], severity=severity))

    return tuple(diagnostics)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(diag.severity in _ERROR_LEVELS for diag in diagnostics)


def _parse_json_line(line: str) -> Diagnostic | object | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return _NON_DIAGNOSTIC_JSON
    if payload.get("$message_type") != "diagnostic":
        return _NON_DIAGNOSTIC_JSON

    message = payload.get("message", "")
    if not message:
        return None

    severity = payload.get("level", "error")
    error_code = _extract_error_code(payload)
    span = _extract_span(payload)

    return Diagnostic(
        message=message,
        severity=severity,
        span=span,
        error_code=error_code,
    )


def _extract_error_code(payload: dict[str, Any]) -> str | None:
    code = payload.get("code")
    if isinstance(code, dict):
        value = code.get("code")
        if isinstance(value, str) and value:
            return value
    return None


def _extract_span(payload: dict[str, Any]) -> tuple[int, int] | None:
    spans = payload.get("spans")
    if not isinstance(spans, list) or not spans:
        return None
    primary = None
    for span in spans:
        if isinstance(span, dict) and span.get("is_primary"):
            primary = span
            break
    if primary is None and isinstance(spans[0], dict):
        primary = spans[0]
    if not isinstance(primary, dict):
        return None
    byte_start = primary.get("byte_start")
    byte_end = primary.get("byte_end")
    if isinstance(byte_start, int) and isinstance(byte_end, int):
        return (byte_start, byte_end)
    return None
