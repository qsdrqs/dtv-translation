from __future__ import annotations

from core.types import Diagnostic


def render_diagnostic(diag: Diagnostic) -> str:
    primary = next((s for s in diag.spans if s.is_primary), None)
    line = primary.line if primary is not None else 0
    col = primary.col if primary is not None else 0
    rule_part = f" ({diag.error_code})" if diag.error_code else ""
    block_lines = [
        f"- L{line}:{col}:    {diag.severity}: {diag.message}{rule_part}",
    ]
    for hint in diag.hints:
        block_lines.append(f"    hint: {hint}")
    return "\n".join(block_lines)
