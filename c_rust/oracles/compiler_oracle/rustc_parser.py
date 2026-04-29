from __future__ import annotations

import json
from typing import Any

from core.types import Diagnostic, DiagnosticSpan
from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult


_ERROR_LEVELS = {"error", "fatal"}


def parse_rustc_diagnostics(result: RustcResult) -> tuple[tuple[Diagnostic, str], ...]:
    """Return (Diagnostic, rendered_text) pairs from rustc's JSON output.

    The rendered text is rustc's own multi-line pretty-printed block (with
    arrows + source highlighting) extracted from `payload["rendered"]`, which
    rustc emits by default under --error-format=json. Empty string when
    rendered is missing (fallback path / non-diagnostic JSON entries).
    """
    pairs: list[tuple[Diagnostic, str]] = []
    fallback_lines: list[str] = []

    for stream in (result.stderr, result.stdout):
        for line in stream.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            pair, consumed = _parse_json_line(stripped)
            if consumed:
                if pair is not None:
                    pairs.append(pair)
                continue
            fallback_lines.append(stripped)

    if not pairs and fallback_lines:
        severity = "error" if result.exit_code != 0 else "warning"
        fallback_diag = Diagnostic(message=fallback_lines[0], severity=severity)
        pairs.append((fallback_diag, fallback_lines[0]))

    return tuple(pairs)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(diag.severity in _ERROR_LEVELS for diag in diagnostics)


def _parse_json_line(line: str) -> tuple[tuple[Diagnostic, str] | None, bool]:
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
    primary_span = _extract_primary_span(payload)
    hints, related_spans = _extract_children_info(payload)
    spans: tuple[DiagnosticSpan, ...] = ()
    if primary_span is not None:
        spans = (primary_span,) + related_spans
    elif related_spans:
        spans = related_spans

    rendered = payload.get("rendered", "")
    if not isinstance(rendered, str):
        rendered = ""

    diag = Diagnostic(
        message=message,
        severity=severity,
        spans=spans,
        error_code=error_code,
        hints=hints,
    )
    return (diag, rendered), True


def _extract_error_code(payload: dict[str, Any]) -> str | None:
    code = payload.get("code")
    if isinstance(code, dict):
        value = code.get("code")
        if isinstance(value, str) and value:
            return value
    return None


def _extract_primary_span(payload: dict[str, Any]) -> DiagnosticSpan | None:
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
    line_start = primary.get("line_start")
    column_start = primary.get("column_start")
    if isinstance(line_start, int):
        return DiagnosticSpan(
            line=line_start,
            col=column_start if isinstance(column_start, int) else 0,
            is_primary=True,
            text=_extract_span_text(primary),
        )
    return None


def _extract_span_text(span: dict[str, Any]) -> str:
    text_field = span.get("text")
    if not isinstance(text_field, list) or not text_field:
        return ""
    first = text_field[0]
    if isinstance(first, dict):
        t = first.get("text")
        if isinstance(t, str):
            return t
    return ""


def _extract_children_info(
    payload: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[DiagnosticSpan, ...]]:
    hints: list[str] = []
    related: list[DiagnosticSpan] = []
    children = payload.get("children")
    _collect_children(children, hints, related)
    return tuple(hints), tuple(related)


def _collect_children(
    children: Any,
    hints: list[str],
    related: list[DiagnosticSpan],
) -> None:
    if not isinstance(children, list):
        return
    for child in children:
        if not isinstance(child, dict):
            continue
        level = child.get("level")
        message = child.get("message", "")
        msg_text = message.strip() if isinstance(message, str) else ""
        if level == "help" and msg_text:
            hints.append(msg_text)
        child_spans = child.get("spans")
        if isinstance(child_spans, list):
            for cs in child_spans:
                if not isinstance(cs, dict):
                    continue
                line_start = cs.get("line_start")
                column_start = cs.get("column_start")
                if isinstance(line_start, int):
                    sr = cs.get("suggested_replacement")
                    related.append(DiagnosticSpan(
                        line=line_start,
                        col=column_start if isinstance(column_start, int) else 0,
                        message=msg_text,
                        text=_extract_span_text(cs),
                        suggested_replacement=sr if isinstance(sr, str) and sr else None,
                    ))
        nested_children = child.get("children")
        _collect_children(nested_children, hints, related)
