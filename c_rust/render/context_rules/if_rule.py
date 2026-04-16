from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.context_rules.base import (
    Analysis,
    ContextRegistry,
    ContextRule,
    PatchPlan,
    TailCompletionKind,
    ancestor_of_type,
    classify_block_tail,
    has_else_clause,
)


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
            if not in_value_context:
                in_value_context = _is_match_arm_value_tail(node, prefix_bytes=prefix_bytes, end_byte=end_byte)
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


def _is_match_arm_value_tail(if_node, *, prefix_bytes: bytes, end_byte: int) -> bool:
    arm_node = ancestor_of_type(if_node, ["match_arm"])
    if arm_node is None:
        return False
    arm_value = arm_node.child_by_field_name("value")
    if arm_value is None or arm_value.type != "block":
        return False
    if not (arm_value.start_byte <= end_byte < arm_value.end_byte):
        return False
    match_node = ancestor_of_type(arm_node, ["match_expression"])
    if match_node is None or not _match_is_in_value_context(match_node, prefix_bytes):
        return False
    completion = classify_block_tail(arm_value, end_byte=end_byte)
    return completion.kind == TailCompletionKind.IF_MISSING_ELSE


def _match_is_in_value_context(match_node, prefix_bytes: bytes) -> bool:
    if ancestor_of_type(
        match_node,
        [
            "let_declaration",
            "let_statement",
            "assignment_expression",
            "return_expression",
            "argument_list",
        ],
    ) is not None:
        return True
    fn_node = ancestor_of_type(match_node, ["function_item"])
    if fn_node is None:
        return False
    body = fn_node.child_by_field_name("body")
    if body is None:
        return False
    header_bytes = prefix_bytes[fn_node.start_byte:body.start_byte]
    if b"->" not in header_bytes:
        return False
    tail = body.named_children[-1] if body.named_children else None
    if tail is None:
        return False
    if tail.id == match_node.id:
        return True
    if tail.type != "expression_statement":
        return False
    inner = tail.named_children[0] if tail.named_children else None
    return inner is not None and inner.id == match_node.id
