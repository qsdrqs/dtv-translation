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
