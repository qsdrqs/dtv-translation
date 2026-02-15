from __future__ import annotations

import json
from typing import Any

from core.types import Diagnostic
from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult


_ERROR_LEVELS = {"error", "fatal"}


def parse_rustc_diagnostics(result: RustcResult) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    fallback_lines: list[str] = []

    for stream in (result.stderr, result.stdout):
        for line in stream.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            diagnostic, consumed = _parse_json_line(stripped)
            if consumed:
                if diagnostic is not None:
                    diagnostics.append(diagnostic)
                continue
            fallback_lines.append(stripped)

    if not diagnostics and fallback_lines:
        severity = "error" if result.exit_code != 0 else "warning"
        diagnostics.append(Diagnostic(message=fallback_lines[0], severity=severity))

    return tuple(diagnostics)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(diag.severity in _ERROR_LEVELS for diag in diagnostics)


def _parse_json_line(line: str) -> tuple[Diagnostic | None, bool]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None, False

    if not isinstance(payload, dict):
        return None, True
    if payload.get("$message_type") != "diagnostic":
        return None, True

    message = payload.get("message", "")
    if not message:
        return None, True

    severity = payload.get("level", "error")
    error_code = _extract_error_code(payload)
    span = _extract_span(payload)
    hints = _extract_hints(payload)

    return (
        Diagnostic(
            message=message,
            severity=severity,
            span=span,
            error_code=error_code,
            hints=hints,
        ),
        True,
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


def _extract_hints(payload: dict[str, Any]) -> tuple[str, ...]:
    hints: list[str] = []
    children = payload.get("children")
    _collect_help_messages(children, hints)
    return tuple(hints)


def _collect_help_messages(children: Any, hints: list[str]) -> None:
    if not isinstance(children, list):
        return
    for child in children:
        if not isinstance(child, dict):
            continue
        level = child.get("level")
        message = child.get("message")
        if level == "help" and isinstance(message, str):
            text = message.strip()
            if text:
                hints.append(text)
        nested_children = child.get("children")
        _collect_help_messages(nested_children, hints)
