from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class PatchPhase(str, Enum):
    SYNTAX = "syntax"
    SEMANTIC = "semantic"



@dataclass(frozen=True)
class IfContext:
    """Analysis hints for an enclosing if-expression."""
    in_expression: bool = False
    missing_else: bool = False  # True if an else branch is required.
    in_consequence: bool = False
    in_alternative: bool = False
    in_value_context: bool = False  # True if the if-expression must yield a value.
    consequence_start: int | None = None  # Byte offset of consequence start.
    consequence_end: int | None = None  # Byte offset of consequence end.
    alternative_start: int | None = None  # Byte offset of alternative start.


@dataclass(frozen=True)
class MatchContext:
    """Analysis hints for an enclosing match-expression."""
    in_expression: bool = False
    in_value_context: bool = False
    in_block: bool = False
    block_start: int | None = None  # Byte offset of match block start.
    block_end: int | None = None  # Byte offset of match block end.
    has_arms: bool = False
    has_wildcard: bool = False
    last_arm_has_comma: bool = False


@dataclass(frozen=True)
class LetContext:
    """Analysis hints for a let binding."""
    in_initializer: bool = False
    has_semicolon: bool = False
    value_block_start: int | None = None  # Byte offset of initializer block start.
    value_end: int | None = None  # Byte offset of initializer end.


@dataclass(frozen=True)
class FunctionContext:
    """Analysis hints for an enclosing function."""
    in_function: bool = False
    returns_value: bool = False
    body_start: int | None = None  # Byte offset of function body start.
    tail_needs_todo: bool = False  # Insert todo!() to satisfy return type.
    tail_needs_semicolon: bool = False  # Ensure trailing semicolon for statements.


@dataclass(frozen=True)
class Analysis:
    """Parsed context info used by patch rules."""
    ok: bool
    notes: str = ""
    end_byte: int = 0  # Byte offset of cursor at end of prefix.
    contexts: dict[str, tuple[object, ...]] = field(default_factory=dict)  # Rule key -> contexts.

    def get(self, key: str) -> tuple[object, ...]:
        return self.contexts.get(key, ())


@dataclass
class Scaffold:
    """Editable scaffold for generating suffix text."""
    closers: tuple[str, ...]
    head_expr: list[str] = field(default_factory=list)  # Prefix additions in expression context.
    head_stmt: list[str] = field(default_factory=list)  # Prefix additions in statement context.
    before: dict[int, list[str]] = field(default_factory=dict)  # Close-idx -> text before closer.
    after: dict[int, list[str]] = field(default_factory=dict)  # Close-idx -> text after closer.

    def _normalize(self, text: str, *, raw: bool = False) -> str:
        if raw or not text:
            return text
        if text.startswith("\n"):
            return text
        return "\n" + text

    def add_head_expr(self, text: str, *, raw: bool = False) -> None:
        self.head_expr.append(self._normalize(text, raw=raw))

    def add_head_stmt(self, text: str, *, raw: bool = False) -> None:
        self.head_stmt.append(self._normalize(text, raw=raw))

    def add_before(self, close_idx: int, text: str) -> None:
        self.before.setdefault(close_idx, []).append(self._normalize(text))

    def add_after(self, close_idx: int, text: str) -> None:
        self.after.setdefault(close_idx, []).append(self._normalize(text))

    def render_head(self) -> str:
        parts: list[str] = []
        parts.extend(self.head_expr)
        parts.extend(self.head_stmt)
        return "".join(parts)

    def render(self) -> str:
        parts: list[str] = []
        parts.append(self.render_head())
        for idx, token in enumerate(self.closers):
            parts.extend(self.before.get(idx, []))
            parts.append(token)
            parts.extend(self.after.get(idx, []))
        return "".join(parts)


@dataclass
class PatchPlan:
    """Mutable plan that accumulates patch operations."""
    prefix: str
    scaffold: Scaffold
    brace_index: dict[int, int]  # Map: brace byte index -> nesting order.
    brace_order_to_close_idx: dict[int, int]  # Map: brace order -> closers index.
    tail_text: str  # prefix + head + tail markers snapshot for parsing.
    tail_markers: list[str] = field(default_factory=list)  # Extra tail markers for parsing.
    notes: list[str] = field(default_factory=list)  # Debug notes from patch rules.

    def __post_init__(self) -> None:
        self._refresh_tail()

    @property
    def brace_count(self) -> int:
        return len(self.brace_order_to_close_idx)

    def index_for(self, start_byte: int | None, *, fallback: int | None = None) -> int | None:
        order: int | None = None
        if start_byte is not None:
            order = self.brace_index.get(start_byte)
        if order is None:
            order = fallback
        if order is None:
            return None
        return self.brace_order_to_close_idx.get(order)

    def insert_before(self, start_byte: int | None, text: str, *, fallback: int | None = None) -> None:
        idx = self.index_for(start_byte, fallback=fallback)
        if idx is None:
            return
        self.scaffold.add_before(idx, text)

    def insert_after(self, start_byte: int | None, text: str, *, fallback: int | None = None) -> None:
        idx = self.index_for(start_byte, fallback=fallback)
        if idx is None:
            return
        self.scaffold.add_after(idx, text)

    def _refresh_tail(self) -> None:
        self.tail_text = self.prefix + self.scaffold.render_head() + "".join(self.tail_markers)

    def add_head_expr(self, text: str, *, raw: bool = False) -> None:
        self.scaffold.add_head_expr(text, raw=raw)
        self._refresh_tail()

    def add_head_stmt(self, text: str, *, raw: bool = False) -> None:
        self.scaffold.add_head_stmt(text, raw=raw)
        self._refresh_tail()

    def add_tail_marker(self, text: str) -> None:
        self.tail_markers.append(text)
        self._refresh_tail()

    def render(self) -> str:
        return self.scaffold.render()


class ContextRegistry:
    def __init__(self) -> None:
        self._data: dict[str, list[object]] = {}

    def add(self, key: str, ctx: object) -> None:
        self._data.setdefault(key, []).append(ctx)

    def freeze(self) -> dict[str, tuple[object, ...]]:
        return {key: tuple(values) for key, values in self._data.items()}


def ancestor_of_type(node, types: Iterable[str]):
    wanted = set(types)
    cur = node
    while cur is not None:
        if cur.type in wanted:
            return cur
        cur = cur.parent
    return None


def ancestor_chain_of_type(node, types: Iterable[str]) -> list:
    wanted = set(types)
    out: list = []
    cur = node
    while cur is not None:
        if cur.type in wanted:
            out.append(cur)
        cur = cur.parent
    return out


def has_else_clause(if_node) -> bool:
    for field in ("alternative", "else_clause"):
        alt = if_node.child_by_field_name(field)
        if alt is not None:
            return True
    for child in if_node.named_children:
        if child.type in {"else_clause", "else"}:
            return True
    return False


def _is_wildcard_match_pattern(pattern_node, prefix_bytes: bytes) -> bool:
    if pattern_node is None:
        return False
    pattern_bytes = prefix_bytes[pattern_node.start_byte:pattern_node.end_byte]
    return pattern_bytes.strip() == b"_"


class ContextRule:
    key: str = ""
    node_types: tuple[str, ...] = ()
    phase: PatchPhase = PatchPhase.SEMANTIC

    def find_nodes(self, anchor) -> list:
        if not self.node_types:
            return []
        return ancestor_chain_of_type(anchor, self.node_types)

    def apply_analysis(self, nodes, *, anchor, end_byte: int, prefix_bytes: bytes, registry: ContextRegistry) -> None:
        raise NotImplementedError

    def get_contexts(self, analysis: Analysis) -> tuple[object, ...]:
        if not self.key:
            return ()
        return analysis.get(self.key)

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        return


class IfContextRule(ContextRule):
    key = "if"
    node_types = ("if_expression",)
    phase = PatchPhase.SEMANTIC

    # Analyze: determine whether each enclosing `if` is missing an else branch and
    # whether the cursor is inside the consequence/alternative, plus whether the
    # `if` is used in a value context. This drives expression-level completion.
    # Patch: ensure expression `if` has an else branch and both branches yield a
    # value by inserting `todo!()` tail expressions when needed. We insert the
    # else clause before the consequence's closing brace so later semicolon
    # insertion can still land after the full `if` expression.
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


class MatchContextRule(ContextRule):
    key = "match"
    node_types = ("match_expression",)
    phase = PatchPhase.SEMANTIC

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
                ),
            )

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        for match_ctx in self.get_contexts(analysis):
            if not isinstance(match_ctx, MatchContext):
                continue
            if not (match_ctx.in_expression and match_ctx.in_block):
                continue
            if match_ctx.has_wildcard:
                continue
            close_idx = plan.index_for(match_ctx.block_start)
            if close_idx is None:
                continue
            text = "_ => todo!()"
            if match_ctx.has_arms and not match_ctx.last_arm_has_comma:
                text = ", _ => todo!()"
            plan.scaffold.add_before(close_idx, text)
            plan.notes.append("render_patch:match_wildcard")


class LetContextRule(ContextRule):
    key = "let"
    node_types = ("let_declaration", "let_statement")
    phase = PatchPhase.SYNTAX

    # Analyze: locate the initializer expression for each enclosing `let` so we can
    # later place a missing semicolon *after* that expression's closing brace.
    # Patch: if the initializer is unfinished and lacks a semicolon, insert one
    # after the initializer's outermost block/if expression to keep the statement
    # well-formed for downstream parsing and compilation.
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
        for idx, ctx in enumerate(self.get_contexts(analysis)):
            if not isinstance(ctx, LetContext):
                continue
            if not ctx.in_initializer or ctx.has_semicolon:
                continue
            value_closed = ctx.value_end is not None and ctx.value_end <= analysis.end_byte
            if value_closed:
                plan.add_head_stmt(";", raw=True)
                plan.notes.append("render_patch:semicolon_head")
                break
            if ctx.value_block_start is None:
                continue
            plan.insert_after(ctx.value_block_start, ";")
            plan.notes.append("render_patch:semicolon")
            plan.add_tail_marker(";")
            break


class FunctionContextRule(ContextRule):
    key = "fn"
    node_types = ("function_item",)
    phase = PatchPhase.SEMANTIC

    # Analyze: detect whether we are inside a function body and whether that
    # function has a non-unit return type (via `->` in the signature).
    # Patch: if the function returns a value and the current tail is a statement,
    # append a `todo!()` tail expression to satisfy the return type.
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
                tail_node = body.named_children[-1] if body.named_children else None
                if tail_node is None:
                    tail_needs_todo = True
                elif tail_node.type == "return_expression":
                    tail_needs_todo = False
                elif tail_node.type == "expression_statement":
                    expr = tail_node.named_children[0] if tail_node.named_children else None
                    if expr is None:
                        tail_needs_todo = True
                        tail_needs_semicolon = True
                    elif expr.type == "if_expression":
                        if has_else_clause(expr):
                            tail_needs_todo = False
                        else:
                            tail_needs_todo = True
                            tail_needs_semicolon = True
                    elif expr.type in {"while_expression", "for_expression"}:
                        tail_needs_todo = True
                        tail_needs_semicolon = True
                    elif expr.type == "return_expression":
                        tail_needs_todo = False
                    else:
                        tail_needs_todo = False
                elif tail_node.type in {"let_declaration", "let_statement", "empty_statement"}:
                    tail_needs_todo = True
                elif tail_node.type.endswith("_item") or tail_node.type == "ERROR":
                    tail_needs_todo = True
                    tail_needs_semicolon = tail_node.type == "ERROR"
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
        # NOTE: We only add a tail expression when the function has an
        # explicit return type. If we later decide to always add a tail
        # `todo!()` even for unit-returning functions, change this rule.
        if not target.tail_needs_todo:
            return
        text = "; todo!()" if target.tail_needs_semicolon else "todo!()"
        plan.insert_before(target.body_start, text, fallback=plan.brace_count - 1)
        plan.notes.append("render_patch:fn_tail")


CONTEXT_RULES: tuple[ContextRule, ...] = (
    IfContextRule(),
    MatchContextRule(),
    LetContextRule(),
    FunctionContextRule(),
)


def apply_patch_rules(
    plan: PatchPlan,
    analysis: Analysis,
    *,
    keys: tuple[str, ...] | None = None,
    phases: tuple[PatchPhase, ...] | None = None,
) -> None:
    for rule in CONTEXT_RULES:
        if keys is not None and rule.key not in keys:
            continue
        if phases is not None and rule.phase not in phases:
            continue
        rule.apply_patch(plan, analysis)
