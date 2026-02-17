from __future__ import annotations

from core.types import RollbackScope
from feedback.repair_context import RepairContext


_GOAL = "Produce a minimal Rust patch that resolves the listed failures."
_CONSTRAINTS = (
    "Keep unchanged code outside the failed snippet.",
    "Return code only. Do not add prose.",
    "Prefer the smallest valid edit.",
)


def render_feedback_prompt(repair_context: RepairContext) -> str:
    diagnostics_block = _render_diagnostics(repair_context)
    constraints_block = "\n".join(f"- {line}" for line in _CONSTRAINTS)
    parser_error_section = ""
    if repair_context.parser_error_context:
        parser_error_section = f"""

Previous parse error:
- {repair_context.parser_error_context}"""
    scope_rules = _scope_rules(repair_context.repair_scope)
    scope_rules_block = "\n".join(f"- {rule}" for rule in scope_rules)
    return f"""The previous generated next code snippet was:

```
{repair_context.failed_snippet}
```

It error with diagnostics:
{diagnostics_block}

Your goal:
- {_GOAL}

repair scope:
- {repair_context.repair_scope.value}

constraints:
{constraints_block}{parser_error_section}

scope rules:
{scope_rules_block}

output contract:
Return exactly one Rust code block:
```rust
<Your patch here>
```
"""


def _render_diagnostics(repair_context: RepairContext) -> str:
    if not repair_context.outputs:
        return "- (no diagnostics)"
    lines: list[str] = []
    for output in repair_context.outputs:
        for diag in output.diagnostics:
            message = diag.message.strip() or "(empty diagnostic)"
            if diag.error_code:
                lines.append(f"- [{output.oracle_name}] {diag.error_code}: {message}")
            else:
                lines.append(f"- [{output.oracle_name}] {message}")
    return "\n".join(lines)


def _scope_rules(scope: RollbackScope) -> tuple[str, ...]:
    if scope == RollbackScope.STMT:
        return (
            "Replace only the failed snippet.",
            "Do not return full function wrappers (for example, `fn main() { ... }`).",
        )
    if scope == RollbackScope.BLOCK:
        return (
            "Patch only the current block.",
            "Do not emit unrelated outer function/module code.",
        )
    if scope == RollbackScope.FUNC:
        return (
            "Patch only the current function.",
            "Do not emit unrelated module-level declarations.",
        )
    return (
        "Patch the full program as needed.",
        "Return one coherent Rust code block only.",
    )
