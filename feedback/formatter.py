from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

from core.types import Diagnostic
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
    # Keep the feedback block anchored at the current generation position,
    # which is best approximated by the first non-empty snippet line.
    block_indent = ""
    for line in repair_context.failed_snippet.splitlines():
        if line.strip():
            block_indent = line[: len(line) - len(line.lstrip(" \t"))]
            break
    diagnostic_blocks = tuple(_iter_diagnostic_blocks(repair_context))
    diagnostics_text = "\n".join(diagnostic_blocks) if diagnostic_blocks else "(no diagnostics)"
    sections: list[str] = []
    if config.include_failed_snippet:
        # Normalize the displayed snippet separately so mixed-indent snippets keep
        # their internal shape without inheriting the block indent twice.
        snippet_indent = _shared_leading_indent(repair_context.failed_snippet)
        failed_snippet = _strip_leading_indent(repair_context.failed_snippet, snippet_indent)
        sections.append(
            f"""failed snippet:
{failed_snippet}"""
        )
    sections.append(
        f"""diagnostics:
{diagnostics_text}"""
    )
    body = "\n\n".join(sections)
    block = f"""/* repair feedback:
{body}
*/"""
    # Indent every non-empty line to match the current generation position.
    if block_indent:
        block = "\n".join(f"{block_indent}{line}" if line else "" for line in block.split("\n"))
    return block


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
    hint_scope = diag.hint_scope.value if diag.hint_scope is not None else None
    primary = next((s for s in diag.spans if s.is_primary), None)
    fields = [
        f"oracle={oracle_name}",
        f"severity={diag.severity}",
        *([f"code={diag.error_code}"] if diag.error_code else []),
        *([f"hint_scope={hint_scope}"] if hint_scope is not None else []),
        *([f"span={primary.line}:{primary.col}"] if primary is not None else []),
    ]
    return " ".join(fields)


def _shared_leading_indent(snippet: str) -> str:
    indent: str | None = None
    for line in snippet.splitlines():
        if not line.strip():
            continue
        line_indent = line[: len(line) - len(line.lstrip(" \t"))]
        if indent is None:
            indent = line_indent
            continue
        # os.path.commonprefix does plain character-by-character comparison
        # with no path-specific logic, so it is safe for whitespace-only strings.
        indent = os.path.commonprefix([indent, line_indent])
        if not indent:
            return ""
    return indent or ""


def _strip_leading_indent(block: str, indent: str) -> str:
    if not indent:
        return block
    lines: list[str] = []
    for line in block.split("\n"):
        if line.startswith(indent):
            lines.append(line[len(indent) :])
            continue
        lines.append(line)
    return "\n".join(lines)

