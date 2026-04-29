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
        diff_injection = _render_minus_prefill(repair_context.failed_snippet) + "+"
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
            'Every line MUST start with "-" (original) or "+" (replacement). '
            "No blank lines, prose, or other content anywhere in the patch, "
            "including at the end of your patch.",
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
        # Feedback A/B is only invoked on error verdicts, so every reachable
        # OracleOutput here MUST carry rendered text parallel to diagnostics.
        # Missing alignment indicates an oracle bug (failed to populate
        # rendered_diagnostics) and we want to fail loudly, not silently
        # downgrade to a stale compact format.
        assert len(output.rendered_diagnostics) == len(output.diagnostics), (
            f"oracle '{output.oracle_name}' returned {len(output.diagnostics)} "
            f"diagnostics but {len(output.rendered_diagnostics)} rendered entries"
        )
        for diag, rendered in zip(output.diagnostics, output.rendered_diagnostics):
            if diag.severity != "error":
                continue
            if rendered:
                lines.append(rendered)
    return "\n".join(lines) if lines else "- (no diagnostics)"


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
