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
class ClosureContext:
    in_closure_body: bool = False
    returns_value: bool = False
    body_start: int | None = None
    tail_completion: TailCompletion = field(
        default_factory=lambda: TailCompletion(kind=TailCompletionKind.COMPLETE)
    )


class ClosureContextRule(ContextRule):
    key = "closure"
    node_types = ("closure_expression",)

    def apply_analysis(self, nodes, *, anchor, end_byte: int, prefix_bytes: bytes, registry: ContextRegistry) -> None:
        for node in nodes:
            body = node.child_by_field_name("body")
            if body is not None and body.type == "block":
                in_closure_body = body.start_byte <= end_byte < body.end_byte
                body_start = body.start_byte
                tail_completion = classify_block_tail(body, end_byte=end_byte)
            else:
                in_closure_body = False
                body_start = None
                tail_completion = TailCompletion(kind=TailCompletionKind.COMPLETE)
            returns_value = node.child_by_field_name("return_type") is not None
            registry.add(
                self.key,
                ClosureContext(
                    in_closure_body=in_closure_body,
                    returns_value=returns_value,
                    body_start=body_start,
                    tail_completion=tail_completion,
                ),
            )

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        target: ClosureContext | None = None
        for ctx in self.get_contexts(analysis):
            if isinstance(ctx, ClosureContext) and ctx.in_closure_body:
                target = ctx
                break
        if target is None or not target.returns_value or target.body_start is None:
            return
        completion = target.tail_completion
        if completion.kind not in {TailCompletionKind.NEEDS_TODO, TailCompletionKind.NEEDS_SEMI_TODO}:
            # COMPLETE: no-op. IF_MISSING_ELSE: IfContextRule handles via
            # value-context detection through closure_expression=VALUE_EXPR.
            return
        text = (
            "; todo!()"
            if completion.kind == TailCompletionKind.NEEDS_SEMI_TODO
            else "todo!()"
        )
        # No fallback: if body_start is missing from brace_index, skip rather
        # than risk inserting at an outer brace (FP-first renderer policy).
        plan.insert_before(target.body_start, text)
        plan.notes.append("render_patch:closure_tail")
