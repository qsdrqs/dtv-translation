from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from core.types import Diagnostic, Granularity
from feedback.feedback import FeedbackState
from feedback.repair_context import RepairContext


@dataclass(frozen=True)
class RepairFeedbackFormatConfig:
    include_failed_snippet: bool = True


def build_repair_feedback(
    feedback_state: FeedbackState,
    bad_snippet: str,
    format_config: RepairFeedbackFormatConfig | None = None,
) -> str:
    repair_context = RepairContext.from_feedback_state(feedback_state, bad_snippet)
    return render_repair_feedback(repair_context, format_config=format_config)


def render_repair_feedback(
    repair_context: RepairContext,
    format_config: RepairFeedbackFormatConfig | None = None,
) -> str:
    config = format_config or RepairFeedbackFormatConfig()
    diagnostic_blocks = tuple(_iter_diagnostic_blocks(repair_context))
    diagnostics_text = "\n".join(diagnostic_blocks) if diagnostic_blocks else "(no diagnostics)"
    sections: list[str] = []
    if config.include_failed_snippet:
        sections.append(
            f"""failed snippet:
{repair_context.failed_snippet}"""
        )
    sections.append(
        f"""diagnostics:
{diagnostics_text}"""
    )
    body = "\n\n".join(sections)
    return f"""/* repair feedback:
{body}
*/"""


def _iter_diagnostic_blocks(repair_context: RepairContext) -> Iterable[str]:
    for output in repair_context.outputs:
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
    primary = next((s for s in diag.spans if s.is_primary), None)
    fields = [
        f"oracle={oracle_name}",
        f"severity={diag.severity}",
        *([f"code={diag.error_code}"] if diag.error_code else []),
        *([f"hint_scope={hint_scope}"] if hint_scope is not None else []),
        *([f"span={primary.line}:{primary.col}"] if primary is not None else []),
    ]
    return " ".join(fields)


def _format_scope(scope: Granularity | None) -> str | None:
    if scope is None:
        return None
    return scope.value
