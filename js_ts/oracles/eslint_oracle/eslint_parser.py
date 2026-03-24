from __future__ import annotations

from core.types import Diagnostic, DiagnosticSpan


def parse_eslint_messages(messages: list[dict]) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for message in messages:
        rule_id = message["ruleId"]
        severity = "error" if message["severity"] == 2 else "warning"
        diagnostics.append(
            Diagnostic(
                message=message["message"],
                severity=severity,
                spans=(DiagnosticSpan(
                    line=message["line"],
                    col=message["column"],
                    is_primary=True,
                ),),
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
        if not _has_primary_span(diag) or _primary_starts_before(diag, prefix_end)
    )


def _has_primary_span(diag: Diagnostic) -> bool:
    return any(s.is_primary for s in diag.spans)


def _primary_starts_before(diag: Diagnostic, limit: tuple[int, int]) -> bool:
    primary = next((s for s in diag.spans if s.is_primary), None)
    if primary is None:
        return True
    limit_line, limit_column = limit
    if primary.line != limit_line:
        return primary.line < limit_line
    return primary.col < limit_column


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
