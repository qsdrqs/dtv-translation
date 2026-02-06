from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.context_rules.base import (
    ContextRule,
    ContextRegistry,
    ancestor_of_type,
    block_tail_needs_todo,
    PatchPlan,
    Analysis,
)


def _is_wildcard_match_pattern(pattern_node, prefix_bytes: bytes) -> bool:
    if pattern_node is None:
        return False
    pattern_bytes = prefix_bytes[pattern_node.start_byte:pattern_node.end_byte]
    return pattern_bytes.strip() == b"_"


@dataclass(frozen=True)
class MatchContext:
    in_expression: bool = False
    in_value_context: bool = False
    in_block: bool = False
    block_start: int | None = None
    block_end: int | None = None
    has_arms: bool = False
    has_wildcard: bool = False
    last_arm_has_comma: bool = False
    cursor_arm_block_start: int | None = None
    cursor_arm_tail_needs_todo: bool = False
    cursor_arm_tail_needs_semicolon: bool = False


class MatchContextRule(ContextRule):
    key = "match"
    node_types = ("match_expression",)

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
            body = node.child_by_field_name("body")
            block_start = body.start_byte if body is not None else None
            block_end = body.end_byte if body is not None else None
            in_block = False
            if body is not None:
                in_block = body.start_byte <= end_byte < body.end_byte

            match_arms = []
            if body is not None:
                for child in body.named_children:
                    if child.type == "match_arm":
                        match_arms.append(child)

            has_arms = bool(match_arms)
            has_wildcard = False
            last_arm_has_comma = False
            for arm in match_arms:
                pattern = arm.child_by_field_name("pattern")
                if _is_wildcard_match_pattern(pattern, prefix_bytes):
                    has_wildcard = True
                    break
            if match_arms:
                last_arm = match_arms[-1]
                arm_bytes = prefix_bytes[last_arm.start_byte:last_arm.end_byte]
                last_arm_has_comma = arm_bytes.rstrip().endswith(b",")

            cursor_arm_block_start: int | None = None
            cursor_arm_tail_needs_todo = False
            cursor_arm_tail_needs_semicolon = False
            if in_value_context:
                for arm in match_arms:
                    arm_value = arm.child_by_field_name("value")
                    if arm_value is None or arm_value.type != "block":
                        continue
                    if not (arm_value.start_byte <= end_byte < arm_value.end_byte):
                        continue
                    needs_todo, needs_semi = block_tail_needs_todo(arm_value)
                    if needs_todo:
                        cursor_arm_block_start = arm_value.start_byte
                        cursor_arm_tail_needs_todo = True
                        cursor_arm_tail_needs_semicolon = needs_semi
                    break

            registry.add(
                self.key,
                MatchContext(
                    in_expression=True,
                    in_value_context=in_value_context,
                    in_block=in_block,
                    block_start=block_start,
                    block_end=block_end,
                    has_arms=has_arms,
                    has_wildcard=has_wildcard,
                    last_arm_has_comma=last_arm_has_comma,
                    cursor_arm_block_start=cursor_arm_block_start,
                    cursor_arm_tail_needs_todo=cursor_arm_tail_needs_todo,
                    cursor_arm_tail_needs_semicolon=cursor_arm_tail_needs_semicolon,
                ),
            )

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        from c_rust.render.context_rules.match_arm_witness_rule import MatchArmTypeWitnessContext

        witness_starts: set[int | None] = {
            ctx.arm_block_start
            for ctx in analysis.get("match_arm_type_witness")
            if isinstance(ctx, MatchArmTypeWitnessContext)
        }

        for match_ctx in self.get_contexts(analysis):
            if not isinstance(match_ctx, MatchContext):
                continue
            if not (match_ctx.in_expression and match_ctx.in_block):
                continue

            if not match_ctx.has_wildcard:
                close_idx = plan.index_for(match_ctx.block_start)
                if close_idx is not None:
                    text = "_ => todo!()"
                    if match_ctx.has_arms and not match_ctx.last_arm_has_comma:
                        text = ", _ => todo!()"
                    plan.scaffold.add_before(close_idx, text)
                    plan.notes.append("render_patch:match_wildcard")

            if match_ctx.cursor_arm_tail_needs_todo:
                if match_ctx.cursor_arm_block_start not in witness_starts:
                    text = "; todo!()" if match_ctx.cursor_arm_tail_needs_semicolon else "todo!()"
                    plan.insert_before(match_ctx.cursor_arm_block_start, text)
                    plan.notes.append("render_patch:match_arm_tail")
