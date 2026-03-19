from __future__ import annotations

from dataclasses import dataclass

from core.types import FeedbackMechanism, FeedbackMode, GenerationChannel
from feedback.formatter import RepairFeedbackFormatConfig, render_repair_feedback
from core.types import RollbackScope
from feedback.language import FeedbackLanguageConfig
from feedback.repair_context import RepairContext


_CONSTRAINTS = (
    "Keep unchanged code outside the failed snippet.",
    "Return code only. Do not add prose.",
    "Prefer the smallest valid edit.",
)


@dataclass(frozen=True)
class FeedbackPlan:
    mechanism: FeedbackMechanism
    mode: FeedbackMode
    channel: GenerationChannel
    prompt: str


def build_feedback_plan(
    *,
    mechanism: FeedbackMechanism,
    requested_mode: FeedbackMode | None,
    repair_context: RepairContext,
    repair_feedback_format_config: RepairFeedbackFormatConfig | None,
    lang_config: FeedbackLanguageConfig,
) -> FeedbackPlan:
    if mechanism == FeedbackMechanism.B:
        return FeedbackPlan(
            mechanism=mechanism,
            mode=FeedbackMode.FENCED,
            channel=GenerationChannel.PATCH,
            prompt=render_feedback_prompt(repair_context, lang_config),
        )
    mode = requested_mode or FeedbackMode.INLINE
    return FeedbackPlan(
        mechanism=mechanism,
        mode=mode,
        channel=GenerationChannel.CONTINUATION,
        prompt=render_repair_feedback(repair_context, format_config=repair_feedback_format_config),
    )


def render_feedback_prompt(
    repair_context: RepairContext,
    lang_config: FeedbackLanguageConfig,
) -> str:
    lang = lang_config.name
    fence_tag = max(lang_config.fence_tags, key=len)
    goal = f"Produce a minimal {lang} patch that resolves the listed failures."
    diagnostics_block = _render_diagnostics(repair_context)
    constraints_block = "\n".join(f"- {line}" for line in _CONSTRAINTS)
    parser_error_section = ""
    if repair_context.parser_error_context:
        parser_error_section = f"""

Previous parse error:
- {repair_context.parser_error_context}"""
    scope_rules = _scope_rules(repair_context.repair_scope, lang_config)
    scope_rules_block = "\n".join(f"- {rule}" for rule in scope_rules)
    return f"""The previous generated next code snippet was:

```
{repair_context.failed_snippet}
```

It error with diagnostics:
{diagnostics_block}

Your goal:
- {goal}

repair scope:
- {repair_context.repair_scope.value}

constraints:
{constraints_block}{parser_error_section}

scope rules:
{scope_rules_block}

output contract:
Return exactly one {lang} code block:
```{fence_tag}
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


def _scope_rules(
    scope: RollbackScope,
    lang_config: FeedbackLanguageConfig,
) -> tuple[str, ...]:
    lang = lang_config.name
    example = lang_config.example_function_wrapper
    if scope == RollbackScope.STMT:
        return (
            "Replace only the failed snippet.",
            f"Do not return full function wrappers (for example, {example}).",
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
        f"Return one coherent {lang} code block only.",
    )
