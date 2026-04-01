from __future__ import annotations

from dataclasses import dataclass

from core.llm_output import AssistantContent, FenceState
from core.types import Granularity
from core.types import FeedbackMechanism, GenerationChannel
from feedback.formatter import RepairFeedbackFormatConfig, render_repair_feedback
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
    channel: GenerationChannel
    prompt: str
    response_prefix: str | AssistantContent | None = None
    post_fence_injection: str | None = None


def build_feedback_plan(
    *,
    mechanism: FeedbackMechanism,
    repair_context: RepairContext,
    repair_feedback_format_config: RepairFeedbackFormatConfig | None,
    lang_config: FeedbackLanguageConfig,
) -> FeedbackPlan:
    if mechanism == FeedbackMechanism.B:
        diff_injection = _render_minus_prefill(repair_context.failed_snippet) + "+ "
        return FeedbackPlan(
            mechanism=mechanism,
            channel=GenerationChannel.PATCH,
            prompt=render_feedback_prompt(repair_context, lang_config, use_stmt_diff=True),
            response_prefix=None,
            post_fence_injection=diff_injection,
        )
    return FeedbackPlan(
        mechanism=mechanism,
        channel=GenerationChannel.CONTINUATION,
        prompt=render_repair_feedback(repair_context, format_config=repair_feedback_format_config),
    )


def render_feedback_prompt(
    repair_context: RepairContext,
    lang_config: FeedbackLanguageConfig,
    *,
    use_stmt_diff: bool = False,
) -> str:
    lang = lang_config.name
    fence_tag = max(lang_config.fence_tags, key=len)
    goal = f"Produce a minimal {lang} patch that resolves the listed failures."
    diagnostics_block = _render_diagnostics(repair_context)
    constraints: list[str] = list(_CONSTRAINTS)
    if use_stmt_diff:
        constraints.extend([
            "Return a unified diff patch for the failed snippet.",
            'Use "-" lines for the current failing snippet and "+" lines for the replacement snippet.',
        ])
    constraints_block = "\n".join(f"- {line}" for line in constraints)
    parser_error_section = ""
    if repair_context.parser_error_context:
        parser_error_section = f"""

Previous parse error:
- {repair_context.parser_error_context}"""
    scope_rules = _scope_rules(repair_context.repair_scope, lang_config)
    scope_rules_block = "\n".join(f"- {rule}" for rule in scope_rules)
    output_contract = f"Return exactly one {lang} code block:"
    if use_stmt_diff:
        output_contract = f"Return exactly one {lang} code block containing the unified diff patch:"
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
{output_contract}
```{fence_tag}
<Your patch here>
```
"""


def _build_response_prefix(
    repair_context: RepairContext,
    lang_config: FeedbackLanguageConfig,
    use_stmt_diff: bool,
) -> AssistantContent:
    if not use_stmt_diff:
        return AssistantContent.empty()
    fence_tag = max(lang_config.fence_tags, key=len)
    diff_lines = _render_minus_prefill(repair_context.failed_snippet)

    # append a single `+` line to guide the model towards producing a diff
    diff_lines += "+ "
    return AssistantContent(
        fence_lang=fence_tag,
        code=diff_lines,
        fence_state=FenceState.INSIDE,
    )


def _render_minus_prefill(snippet: str) -> str:
    lines = snippet.splitlines()
    if not lines:
        return "-\n"
    return "".join(f"- {line}\n" for line in lines)


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
    scope: Granularity,
    lang_config: FeedbackLanguageConfig,
) -> tuple[str, ...]:
    lang = lang_config.name
    example = lang_config.example_function_wrapper
    if scope == Granularity.STMT:
        return (
            "Replace only the failed snippet.",
            f"Do not return full function wrappers (for example, {example}).",
        )
    if scope == Granularity.BLOCK:
        return (
            "Patch only the current block.",
            "Do not emit unrelated outer function/module code.",
        )
    if scope == Granularity.FUNC:
        return (
            "Patch only the current function.",
            "Do not emit unrelated module-level declarations.",
        )
    return (
        "Patch the full program as needed.",
        f"Return one coherent {lang} code block only.",
    )
