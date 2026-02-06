from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.context_rules.base import ContextRule, ContextRegistry, block_tail_needs_todo, PatchPlan, Analysis


@dataclass(frozen=True)
class FunctionContext:
    in_function: bool = False
    returns_value: bool = False
    body_start: int | None = None
    tail_needs_todo: bool = False
    tail_needs_semicolon: bool = False


class FunctionContextRule(ContextRule):
    key = "fn"
    node_types = ("function_item",)

    def apply_analysis(self, nodes, *, anchor, end_byte: int, prefix_bytes: bytes, registry: ContextRegistry) -> None:
        for node in nodes:
            body = node.child_by_field_name("body")
            if body is not None:
                in_function = body.start_byte <= end_byte < body.end_byte
                header_end = body.start_byte
                body_start = body.start_byte
            else:
                header_end = node.end_byte
                in_function = False
                body_start = None
            header = prefix_bytes[node.start_byte:header_end]
            tail_needs_todo = False
            tail_needs_semicolon = False
            if body is not None:
                tail_needs_todo, tail_needs_semicolon = block_tail_needs_todo(body)
            registry.add(
                self.key,
                FunctionContext(
                    in_function=in_function,
                    returns_value=b"->" in header,
                    body_start=body_start,
                    tail_needs_todo=tail_needs_todo,
                    tail_needs_semicolon=tail_needs_semicolon,
                ),
            )

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        target: FunctionContext | None = None
        for ctx in self.get_contexts(analysis):
            if isinstance(ctx, FunctionContext) and ctx.in_function:
                target = ctx
                break
        if target is None or not target.returns_value:
            return
        if not target.tail_needs_todo:
            return
        text = "; todo!()" if target.tail_needs_semicolon else "todo!()"
        plan.insert_before(target.body_start, text, fallback=plan.brace_count - 1)
        plan.notes.append("render_patch:fn_tail")
