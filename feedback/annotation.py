from __future__ import annotations

from collections.abc import Iterable

from core.types import Diagnostic, DiagnosticSpan


def annotate_snippet(
    snippet: str,
    snippet_start_line: int,
    diagnostics: Iterable[Diagnostic],
    comment_prefix: str = "//",
) -> str:
    if not snippet:
        return snippet

    annotations: dict[int, list[str]] = {}
    for diag in diagnostics:
        code = diag.error_code or ""
        for span in diag.spans:
            line_in_snippet = span.line - snippet_start_line
            if line_in_snippet < 0:
                continue
            message = span.message or diag.message
            label = _build_label(code, message)
            if label:
                annotations.setdefault(line_in_snippet, []).append(label)

    if not annotations:
        return snippet

    lines = snippet.split("\n")
    for idx in sorted(annotations):
        if idx >= len(lines):
            continue
        combined = "; ".join(annotations[idx])
        lines[idx] = f"{lines[idx]}  {comment_prefix} <-- {combined}"
    return "\n".join(lines)


def _build_label(error_code: str, message: str) -> str:
    parts: list[str] = []
    if error_code:
        parts.append(f"error: {error_code}")
    if message:
        if parts:
            parts.append(f": {message}")
        else:
            parts.append(message)
    if not parts:
        parts.append("error here")
    return "".join(parts)
