from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.context_rules.base import ContextRule, ContextRegistry, PatchPlan, Analysis, PatchPhase


@dataclass(frozen=True)
class LetContext:
    in_initializer: bool = False
    has_semicolon: bool = False
    value_block_start: int | None = None
    value_end: int | None = None


class LetContextRule(ContextRule):
    key = "let"
    node_types = ("let_declaration",)
    phase = PatchPhase.SYNTAX

    def apply_analysis(self, nodes, *, anchor, end_byte: int, prefix_bytes: bytes, registry: ContextRegistry) -> None:
        for node in nodes:
            node_bytes = prefix_bytes[node.start_byte:node.end_byte]
            has_semicolon = node_bytes.rstrip().endswith(b";")
            value_node = node.child_by_field_name("value")
            in_initializer = value_node is not None and value_node.start_byte <= end_byte
            value_block_start: int | None = None
            value_end: int | None = None
            if value_node is not None:
                value_end = value_node.end_byte
                if value_node.type == "block":
                    value_block_start = value_node.start_byte
                elif value_node.type == "if_expression":
                    alt = None
                    for field in ("alternative", "else_clause"):
                        alt = value_node.child_by_field_name(field)
                        if alt is not None:
                            break
                    if alt is not None:
                        if alt.type == "block":
                            value_block_start = alt.start_byte
                        else:
                            body = alt.child_by_field_name("body")
                            if body is not None and body.type == "block":
                                value_block_start = body.start_byte
                            elif alt.named_children and alt.named_children[0].type == "block":
                                value_block_start = alt.named_children[0].start_byte
                    if value_block_start is None:
                        cons = value_node.child_by_field_name("consequence")
                        if cons is not None and cons.type == "block":
                            value_block_start = cons.start_byte
                elif value_node.type == "match_expression":
                    match_block = value_node.child_by_field_name("body")
                    if match_block is not None and match_block.type == "match_block":
                        value_block_start = match_block.start_byte
                elif value_node.type == "closure_expression":
                    body = value_node.child_by_field_name("body")
                    if body is not None and body.type == "block":
                        value_block_start = body.start_byte

            registry.add(
                self.key,
                LetContext(
                    in_initializer=in_initializer,
                    has_semicolon=has_semicolon,
                    value_block_start=value_block_start,
                    value_end=value_end,
                ),
            )

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        # Patch every unclosed let_declaration ancestor; nested lets need
        # independent insertion points.
        head_semicolon_added = False
        for idx, ctx in enumerate(self.get_contexts(analysis)):
            if not isinstance(ctx, LetContext):
                continue
            if not ctx.in_initializer or ctx.has_semicolon:
                continue
            value_closed = ctx.value_end is not None and ctx.value_end <= analysis.end_byte
            if value_closed:
                if head_semicolon_added:
                    continue
                plan.add_head_stmt(";", raw=True)
                plan.notes.append("render_patch:semicolon_head")
                head_semicolon_added = True
                continue
            if ctx.value_block_start is None:
                continue
            plan.insert_after(ctx.value_block_start, ";")
            plan.notes.append("render_patch:semicolon")
            plan.add_tail_marker(";")
