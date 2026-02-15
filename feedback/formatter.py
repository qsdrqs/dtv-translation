from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from core.types import Diagnostic, RollbackScope
from feedback.feedback import FeedbackState


@dataclass(frozen=True)
class RepairFeedbackFormatConfig:
    include_failed_snippet: bool = True


def build_repair_feedback(
    feedback_state: FeedbackState,
    bad_snippet: str,
    format_config: RepairFeedbackFormatConfig | None = None,
) -> str:
    config = format_config or RepairFeedbackFormatConfig()
    diagnostic_blocks = tuple(_iter_diagnostic_blocks(feedback_state))
    diagnostics_text = "\n".join(diagnostic_blocks) if diagnostic_blocks else "(no diagnostics)"
    sections: list[str] = []
    if config.include_failed_snippet:
        snippet = bad_snippet.strip() or "(empty)"
        sections.append(
            f"""failed snippet:
{snippet}"""
        )
    sections.append(
        f"""diagnostics:
{diagnostics_text}"""
    )
    body = "\n\n".join(sections)
    return f"""/* repair feedback:
{body}
*/"""


def _iter_diagnostic_blocks(feedback_state: FeedbackState) -> Iterable[str]:
    for output in feedback_state.recent_outputs:
        for diag in output.diagnostics:
            header = _build_header(output.oracle_name, diag)
            hints = tuple(hint.strip() for hint in diag.hints if hint.strip())
            hints_block = ""
            if hints:
                hint_lines = "\n".join(f"  - {hint}" for hint in hints)
                hints_block = f"""
hints:
{hint_lines}"""
            yield f"""- {header}
message: {diag.message}{hints_block}"""


def _build_header(oracle_name: str, diag: Diagnostic) -> str:
    hint_scope = _format_scope(diag.hint_scope)
    fields = [
        f"oracle={oracle_name}",
        f"severity={diag.severity}",
        *([f"code={diag.error_code}"] if diag.error_code else []),
        *([f"hint_scope={hint_scope}"] if hint_scope is not None else []),
        *([f"span={diag.span[0]}:{diag.span[1]}"] if diag.span is not None else []),
    ]
    return " ".join(fields)


def _format_scope(scope: RollbackScope | None) -> str | None:
    if scope is None:
        return None
    return scope.value
