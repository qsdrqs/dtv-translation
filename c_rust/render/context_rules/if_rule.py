from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.context_rules.base import ContextRule, ContextRegistry, ancestor_of_type, has_else_clause, PatchPlan, Analysis


@dataclass(frozen=True)
class IfContext:
    in_expression: bool = False
    missing_else: bool = False
    in_consequence: bool = False
    in_alternative: bool = False
    in_value_context: bool = False
    consequence_start: int | None = None
    consequence_end: int | None = None
    alternative_start: int | None = None


class IfContextRule(ContextRule):
    key = "if"
    node_types = ("if_expression",)

    def apply_analysis(self, nodes, *, anchor, end_byte: int, prefix_bytes: bytes, registry: ContextRegistry) -> None:
        for node in nodes:
            in_value_context = ancestor_of_type(
                node,
                [
                    "let_declaration",
                    "let_statement",
                    "assignment_expression",
                    "return_expression",
                    "argument_list",
                ],
            ) is not None
            missing_else = not has_else_clause(node)
            in_consequence = False
            in_alternative = False
            consequence = node.child_by_field_name("consequence")
            consequence_start = consequence.start_byte if consequence is not None else None
            consequence_end = consequence.end_byte if consequence is not None else None
            if consequence is not None:
                in_consequence = consequence.start_byte <= end_byte < consequence.end_byte
            alternative = None
            for field in ("alternative", "else_clause"):
                alternative = node.child_by_field_name(field)
                if alternative is not None:
                    break
            alternative_start = None
            if alternative is not None:
                in_alternative = alternative.start_byte <= end_byte < alternative.end_byte
                if alternative.type == "block":
                    alternative_start = alternative.start_byte

            registry.add(
                self.key,
                IfContext(
                    in_expression=True,
                    missing_else=missing_else,
                    in_consequence=in_consequence,
                    in_alternative=in_alternative,
                    in_value_context=in_value_context,
                    consequence_start=consequence_start,
                    consequence_end=consequence_end,
                    alternative_start=alternative_start,
                ),
            )

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        for idx, if_ctx in enumerate(self.get_contexts(analysis)):
            if not isinstance(if_ctx, IfContext):
                continue
            if not (if_ctx.in_expression and if_ctx.in_value_context):
                continue
            if if_ctx.missing_else:
                consequence_closed = (
                    if_ctx.consequence_end is not None and if_ctx.consequence_end <= analysis.end_byte
                )
                if consequence_closed:
                    plan.add_head_expr(" else { todo!() }", raw=True)
                    plan.notes.append("render_patch:if_else_head")
                else:
                    if if_ctx.in_consequence:
                        plan.insert_before(if_ctx.consequence_start, "todo!()")
                    plan.insert_before(if_ctx.consequence_start, "} else { todo!()")
                    plan.notes.append("render_patch:if_else")
            elif if_ctx.in_alternative:
                plan.insert_before(if_ctx.alternative_start, "todo!()", fallback=idx)
                plan.notes.append("render_patch:if_else_tail")
