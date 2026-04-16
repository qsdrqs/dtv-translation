from __future__ import annotations

from dataclasses import dataclass, field

from c_rust.render.context_rules.base import (
    Analysis,
    ContextRegistry,
    ContextRule,
    PatchPlan,
    TailCompletion,
    TailCompletionKind,
    classify_block_tail,
)


@dataclass(frozen=True)
class FunctionContext:
    in_function: bool = False
    returns_value: bool = False
    body_start: int | None = None
    tail_completion: TailCompletion = field(
        default_factory=lambda: TailCompletion(kind=TailCompletionKind.COMPLETE)
    )


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
            tail_completion = TailCompletion(kind=TailCompletionKind.COMPLETE)
            if body is not None:
                tail_completion = classify_block_tail(body, end_byte=end_byte)
            registry.add(
                self.key,
                FunctionContext(
                    in_function=in_function,
                    returns_value=b"->" in header,
                    body_start=body_start,
                    tail_completion=tail_completion,
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
        completion = target.tail_completion
        if (
            completion.kind == TailCompletionKind.IF_MISSING_ELSE
            and completion.if_consequence_start is not None
        ):
            consequence_closed = (
                completion.if_consequence_end is not None
                and completion.if_consequence_end <= analysis.end_byte
            )
            if consequence_closed:
                plan.add_head_expr(" else { todo!() };", raw=True)
                plan.add_head_stmt("todo!()")
                plan.notes.append("render_patch:fn_tail_if_else_head")
            else:
                if completion.if_in_consequence:
                    plan.insert_before(completion.if_consequence_start, "todo!()")
                plan.insert_before(completion.if_consequence_start, "} else { todo!()")
                plan.notes.append("render_patch:fn_tail_if_else")
            return
        if completion.kind == TailCompletionKind.COMPLETE:
            return
        if completion.kind not in {
            TailCompletionKind.NEEDS_TODO,
            TailCompletionKind.NEEDS_SEMI_TODO,
        }:
            return
        text = (
            "; todo!()"
            if completion.kind == TailCompletionKind.NEEDS_SEMI_TODO
            else "todo!()"
        )
        plan.insert_before(target.body_start, text, fallback=plan.brace_count - 1)
        plan.notes.append("render_patch:fn_tail")
