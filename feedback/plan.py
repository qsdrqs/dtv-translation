from __future__ import annotations

from dataclasses import dataclass

from core.llm_output import AssistantContent, DEFAULT_WRITE_REGION_MARKERS, WriteRegionMarkers, WriteRegionState
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
    post_region_injection: str | None = None


def build_feedback_plan(
    *,
    mechanism: FeedbackMechanism,
    repair_context: RepairContext,
    repair_feedback_format_config: RepairFeedbackFormatConfig | None,
    lang_config: FeedbackLanguageConfig,
    write_region_markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
) -> FeedbackPlan:
    if mechanism == FeedbackMechanism.B:
        diff_injection = _render_minus_prefill(repair_context.failed_snippet) + "+ "
        return FeedbackPlan(
            mechanism=mechanism,
            channel=GenerationChannel.PATCH,
            prompt=render_feedback_prompt(
                repair_context,
                lang_config,
                use_stmt_diff=True,
                write_region_markers=write_region_markers,
            ),
            response_prefix=None,
            post_region_injection=diff_injection,
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
    write_region_markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
) -> str:
    lang = lang_config.name
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
    output_contract = f"Return exactly one write-code region containing raw {lang} text:"
    if use_stmt_diff:
        output_contract = "Return exactly one write-code region containing the unified diff patch:"
    return f"""The previous generated next code snippet was:

{write_region_markers.begin_marker}
{repair_context.failed_snippet}
{write_region_markers.end_marker}

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
{write_region_markers.begin_marker}
<Your patch here>
{write_region_markers.end_marker}
"""


def _build_response_prefix(
    repair_context: RepairContext,
    lang_config: FeedbackLanguageConfig,
    use_stmt_diff: bool,
    write_region_markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
) -> AssistantContent:
    if not use_stmt_diff:
        return AssistantContent.empty()
    diff_lines = _render_minus_prefill(repair_context.failed_snippet)

    diff_lines += "+ "
    return AssistantContent(
        code=diff_lines,
        has_begin_marker=True,
        region_state=WriteRegionState.INSIDE,
        markers=write_region_markers,
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
            hints = tuple(hint.strip() for hint in diag.hints if hint.strip())
            if diag.error_code:
                line = f"- [{output.oracle_name}] {diag.error_code}: {message}"
            else:
                line = f"- [{output.oracle_name}] {message}"
            if hints:
                hint_lines = "\n".join(f"  hint: {hint}" for hint in hints)
                line = f"{line}\n{hint_lines}"
            lines.append(line)
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
        f"Return one coherent {lang} write region only.",
    )
