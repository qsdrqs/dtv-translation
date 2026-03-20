from __future__ import annotations

from core.types import Diagnostic


def parse_eslint_messages(messages: list[dict]) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for message in messages:
        rule_id = message["ruleId"]
        severity = "error" if message["severity"] == 2 else "warning"
        diagnostics.append(
            Diagnostic(
                message=f"[{rule_id}] {message['message']}",
                severity=severity,
                span=(message["line"], message["column"]),
                error_code=rule_id,
            )
        )
    return tuple(diagnostics)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(diag.severity == "error" for diag in diagnostics)


def filter_post_prefix_diagnostics(
    diagnostics: tuple[Diagnostic, ...],
    prefix: str,
) -> tuple[Diagnostic, ...]:
    prefix_end = _prefix_end_span(prefix)
    return tuple(
        diag for diag in diagnostics
        if diag.span is None or _span_starts_before(diag.span, prefix_end)
    )


def _prefix_end_span(prefix: str) -> tuple[int, int]:
    line = 1
    column = 1
    for ch in prefix:
        if ch == "\n":
            line += 1
            column = 1
            continue
        column += 1
    return (line, column)


def _span_starts_before(span: tuple[int, int], limit: tuple[int, int]) -> bool:
    line, column = span
    limit_line, limit_column = limit
    if line != limit_line:
        return line < limit_line
    return column < limit_column
