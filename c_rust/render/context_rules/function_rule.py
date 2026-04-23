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
        # Cascade over every enclosing function_item: scaffold force-closes all
        # unclosed fn bodies, so each non-unit-returning one needs its own tail
        # patch. Innermost-only first-break leaves outer fn tails dangling (the
        # nested fn item yields `()`), producing scaffold-caused E0308 FPs.
        # No fallback on body_start lookup: mis-routing `todo!()` to an outer
        # brace in the cascade would create a scaffold bug that rejects legal
        # prefixes (mirrors closure_rule.py policy).
        for ctx in self.get_contexts(analysis):
            if not isinstance(ctx, FunctionContext) or not ctx.returns_value:
                continue
            completion = ctx.tail_completion
            if completion.kind == TailCompletionKind.COMPLETE:
                continue
            if (
                completion.kind == TailCompletionKind.IF_MISSING_ELSE
                and completion.if_consequence_start is not None
            ):
                # Both branches downgrade the chain to a statement (`;`) + independent
                # `todo!()` fn tail. Required for else-if chains where sibling arms we
                # don't patch may have type `()` and would pollute the chain type.
                # Tradeoff: downgrading hides type errors in a user-intended tail value
                # (demotes E0308 to unused-value warning). Acceptable here because the
                # patch is scaffold padding; the consequence gets rechecked as DTV
                # generates more statements.
                if completion.if_in_consequence:
                    plan.insert_before(completion.if_consequence_start, "todo!()")
                consequence_closed = (
                    completion.if_consequence_end is not None
                    and completion.if_consequence_end <= analysis.end_byte
                )
                if consequence_closed:
                    plan.add_head_expr(" else { todo!() };", raw=True)
                    plan.add_head_stmt("todo!()")
                    plan.notes.append("render_patch:fn_tail_if_else_head")
                else:
                    plan.insert_before(completion.if_consequence_start, "} else { todo!()")
                    plan.insert_after(completion.if_consequence_start, ";")
                    plan.insert_before(ctx.body_start, "todo!()")
                    plan.notes.append("render_patch:fn_tail_if_else")
                continue
            if completion.kind not in {
                TailCompletionKind.NEEDS_TODO,
                TailCompletionKind.NEEDS_SEMI_TODO,
            }:
                continue
            text = (
                "; todo!()"
                if completion.kind == TailCompletionKind.NEEDS_SEMI_TODO
                else "todo!()"
            )
            plan.insert_before(ctx.body_start, text)
            plan.notes.append("render_patch:fn_tail")
