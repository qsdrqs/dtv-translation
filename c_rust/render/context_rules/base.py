from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class PatchPhase(str, Enum):
    SYNTAX = "syntax"
    SEMANTIC = "semantic"


class TailCompletionKind(str, Enum):
    COMPLETE = "complete"
    IF_MISSING_ELSE = "if_missing_else"
    NEEDS_TODO = "needs_todo"
    NEEDS_SEMI_TODO = "needs_semi_todo"


class NodeKind(str, Enum):
    # Ancestor whose presence proves the descendant is in a value context
    # (let/return/assignment/argument). `find_value_context` stops here.
    VALUE_CTX_ANCESTOR = "value_ctx_ancestor"
    # Tail-forwarding wrapper: its value equals the tail value of its inner
    # block/expression. `find_value_context` verifies tail position and
    # continues upward through it.
    TAIL_FORWARDING = "tail_forwarding"
    # Branching expression (if/match): its value equals the value of the
    # selected branch. `find_value_context` verifies branch-tail position and
    # continues upward.
    BRANCHING = "branching"
    # Wraps the inner value in a different type (Future<T>/Result<T,E>/...).
    # For now we stop here without attempting Future/Result awareness.
    VALUE_WRAPPING = "value_wrapping"
    # Loop expression with a body block. Yields `()` (for/while) or `!`/
    # `break X` type (loop). Not a value-context source. Renderer downgrades
    # as fn tail (block value type rarely matches non-() fn return).
    LOOPING = "looping"
    # Control-flow leaf (break/continue). Yields `!`. Not a value-context
    # source. Cannot appear as direct fn body tail in valid Rust (must be
    # nested inside a loop).
    CONTROL_LEAF = "control_leaf"
    # `expression_statement`: conditional on whether a trailing `;` is present.
    # `find_value_context` resolves this at runtime.
    STATEMENT_WRAPPER = "statement_wrapper"
    # `function_item` / `match_arm`: value context only if the descendant is
    # at the respective tail position AND the outer context demands a value.
    # `find_value_context` dispatches on the specific node type.
    FN_BODY_OR_ARM = "fn_body_or_arm"
    # Atomic expression nodes - literals, identifiers. Cannot appear as
    # non-trivial ancestors during context walking.
    LEAF = "leaf"
    # Any other value-producing expression whose children sit in a value
    # context (binary_expression, call_expression, field_expression, ...).
    # `find_value_context` keeps walking upward through these.
    VALUE_EXPR = "value_expr"


# Single source of truth for how each tree-sitter-rust node type affects
# value-context analysis. Covers every subtype of the `_expression` supertype
# plus the non-expression ancestor node types that appear in parent chains
# during context rule analysis. The meta-test in
# `test/c_rust/test_node_classification.py` enforces completeness against the
# grammar and catches stale entries on tree-sitter upgrades.
NODE_CLASSIFICATION: dict[str, NodeKind] = {
    # VALUE_CTX_ANCESTOR
    "let_declaration":          NodeKind.VALUE_CTX_ANCESTOR,
    "assignment_expression":    NodeKind.VALUE_CTX_ANCESTOR,
    "compound_assignment_expr": NodeKind.VALUE_CTX_ANCESTOR,
    "return_expression":        NodeKind.VALUE_CTX_ANCESTOR,
    "arguments":                NodeKind.VALUE_CTX_ANCESTOR,
    # TAIL_FORWARDING
    "block":                    NodeKind.TAIL_FORWARDING,
    "unsafe_block":             NodeKind.TAIL_FORWARDING,
    "const_block":              NodeKind.TAIL_FORWARDING,
    "parenthesized_expression": NodeKind.TAIL_FORWARDING,
    # BRANCHING
    "if_expression":            NodeKind.BRANCHING,
    "match_expression":         NodeKind.BRANCHING,
    # VALUE_WRAPPING
    "async_block":              NodeKind.VALUE_WRAPPING,
    "try_block":                NodeKind.VALUE_WRAPPING,
    "gen_block":                NodeKind.VALUE_WRAPPING,
    # LOOPING
    "for_expression":           NodeKind.LOOPING,
    "while_expression":         NodeKind.LOOPING,
    "loop_expression":          NodeKind.LOOPING,
    # CONTROL_LEAF
    "break_expression":         NodeKind.CONTROL_LEAF,
    "continue_expression":      NodeKind.CONTROL_LEAF,
    # STATEMENT_WRAPPER
    "expression_statement":     NodeKind.STATEMENT_WRAPPER,
    # FN_BODY_OR_ARM
    "function_item":            NodeKind.FN_BODY_OR_ARM,
    "match_arm":                NodeKind.FN_BODY_OR_ARM,
    # LEAF
    "boolean_literal":          NodeKind.LEAF,
    "char_literal":             NodeKind.LEAF,
    "float_literal":            NodeKind.LEAF,
    "integer_literal":          NodeKind.LEAF,
    "raw_string_literal":       NodeKind.LEAF,
    "string_literal":           NodeKind.LEAF,
    "identifier":               NodeKind.LEAF,
    "scoped_identifier":        NodeKind.LEAF,
    "self":                     NodeKind.LEAF,
    "metavariable":             NodeKind.LEAF,
    "unit_expression":          NodeKind.LEAF,
    "generic_function":         NodeKind.LEAF,
    # VALUE_EXPR (everything else: propagate upward by default)
    "array_expression":         NodeKind.VALUE_EXPR,
    "await_expression":         NodeKind.VALUE_EXPR,
    "binary_expression":        NodeKind.VALUE_EXPR,
    "call_expression":          NodeKind.VALUE_EXPR,
    "closure_expression":       NodeKind.VALUE_EXPR,
    "field_expression":         NodeKind.VALUE_EXPR,
    "index_expression":         NodeKind.VALUE_EXPR,
    "macro_invocation":         NodeKind.VALUE_EXPR,
    "range_expression":         NodeKind.VALUE_EXPR,
    "reference_expression":     NodeKind.VALUE_EXPR,
    "struct_expression":        NodeKind.VALUE_EXPR,
    "try_expression":           NodeKind.VALUE_EXPR,
    "tuple_expression":         NodeKind.VALUE_EXPR,
    "type_cast_expression":     NodeKind.VALUE_EXPR,
    "unary_expression":         NodeKind.VALUE_EXPR,
    "yield_expression":         NodeKind.VALUE_EXPR,
}


class ValueContextReason(str, Enum):
    LET = "let"
    ASSIGNMENT = "assignment"
    RETURN = "return"
    ARGUMENT = "argument"
    FN_BODY_TAIL = "fn_body_tail"
    MATCH_ARM_VALUE = "match_arm_value"


@dataclass(frozen=True)
class ValueContextInfo:
    reason: ValueContextReason


_FN_TAIL_DOWNGRADE_KINDS: frozenset[NodeKind] = frozenset({
    NodeKind.LOOPING,
    NodeKind.BRANCHING,
})


_ANCESTOR_TO_REASON: dict[str, ValueContextReason] = {
    "let_declaration":          ValueContextReason.LET,
    "assignment_expression":    ValueContextReason.ASSIGNMENT,
    "compound_assignment_expr": ValueContextReason.ASSIGNMENT,
    "return_expression":        ValueContextReason.RETURN,
    "arguments":                ValueContextReason.ARGUMENT,
}


def _ancestor_of_type_single(node, type_name: str):
    cur = node.parent
    while cur is not None:
        if cur.type == type_name:
            return cur
        cur = cur.parent
    return None


def _inner_block_of_wrapper(wrapper):
    if wrapper.type == "block":
        return wrapper
    for c in wrapper.children:
        if c.type == "block":
            return c
    return None


def _child_is_wrapper_tail(child, wrapper) -> bool:
    if wrapper.type == "parenthesized_expression":
        return bool(wrapper.named_children) and wrapper.named_children[0].id == child.id
    inner = _inner_block_of_wrapper(wrapper)
    if inner is None:
        return False
    if inner.id == child.id:
        return True
    return bool(inner.named_children) and inner.named_children[-1].id == child.id


def _child_is_if_branch_tail(child, if_node) -> bool:
    for field in ("consequence", "alternative"):
        target = if_node.child_by_field_name(field)
        if target is None:
            continue
        if target.id == child.id:
            return True
        if target.type == "block":
            if target.named_children and target.named_children[-1].id == child.id:
                return True
        elif target.type == "else_clause":
            for sub in target.named_children:
                if sub.id == child.id:
                    return True
                if sub.type == "block" and sub.named_children and sub.named_children[-1].id == child.id:
                    return True
    return False


def _fn_body_tail_info(child, fn_node, prefix_bytes: bytes) -> ValueContextInfo | None:
    body = fn_node.child_by_field_name("body")
    if body is None or body.id != child.id:
        return None
    header_bytes = prefix_bytes[fn_node.start_byte:body.start_byte]
    if b"->" not in header_bytes:
        return None
    return ValueContextInfo(reason=ValueContextReason.FN_BODY_TAIL)


def _match_arm_value_info(child, arm_node, prefix_bytes: bytes) -> ValueContextInfo | None:
    arm_value = arm_node.child_by_field_name("value")
    if arm_value is None or arm_value.id != child.id:
        return None
    match_node = _ancestor_of_type_single(arm_node, "match_expression")
    if match_node is None:
        return None
    if find_value_context(match_node, prefix_bytes) is None:
        return None
    return ValueContextInfo(reason=ValueContextReason.MATCH_ARM_VALUE)


def find_value_context(node, prefix_bytes: bytes) -> ValueContextInfo | None:
    """Walk `node`'s ancestor chain to determine whether it sits in a value context.

    Returns a `ValueContextInfo` with the reason that settled the decision, or
    `None` when the ancestor chain blocks value-context propagation.

    Dispatch is driven by `NODE_CLASSIFICATION`; see the `NodeKind` docstrings
    for the role of each category. Unknown node types (not expected after the
    Layer A meta-test) return `None` defensively.
    """
    child = node
    parent = node.parent
    while parent is not None:
        kind = NODE_CLASSIFICATION.get(parent.type)

        if kind == NodeKind.VALUE_CTX_ANCESTOR:
            reason = _ANCESTOR_TO_REASON.get(parent.type)
            if reason is None:
                return None
            return ValueContextInfo(reason=reason)

        if kind == NodeKind.TAIL_FORWARDING:
            if not _child_is_wrapper_tail(child, parent):
                return None
            child, parent = parent, parent.parent
            continue

        if kind == NodeKind.BRANCHING:
            if parent.type == "if_expression":
                if not _child_is_if_branch_tail(child, parent):
                    return None
                child, parent = parent, parent.parent
                continue
            return None

        if kind == NodeKind.STATEMENT_WRAPPER:
            if any(c.type == ";" for c in parent.children):
                return None
            child, parent = parent, parent.parent
            continue

        if kind == NodeKind.FN_BODY_OR_ARM:
            if parent.type == "function_item":
                return _fn_body_tail_info(child, parent, prefix_bytes)
            if parent.type == "match_arm":
                return _match_arm_value_info(child, parent, prefix_bytes)
            return None

        if kind == NodeKind.VALUE_EXPR:
            child, parent = parent, parent.parent
            continue

        if kind in (
            NodeKind.LOOPING,
            NodeKind.CONTROL_LEAF,
            NodeKind.VALUE_WRAPPING,
            NodeKind.LEAF,
        ):
            return None

        return None

    return None


@dataclass(frozen=True)
class Analysis:
    ok: bool
    notes: str = ""
    end_byte: int = 0
    contexts: dict[str, tuple[object, ...]] = field(default_factory=dict)

    def get(self, key: str) -> tuple[object, ...]:
        return self.contexts.get(key, ())


@dataclass(frozen=True)
class TailCompletion:
    kind: TailCompletionKind
    if_consequence_start: int | None = None
    if_consequence_end: int | None = None
    if_in_consequence: bool = False


class ContextRegistry:
    def __init__(self) -> None:
        self._data: dict[str, list[object]] = {}

    def add(self, key: str, ctx: object) -> None:
        self._data.setdefault(key, []).append(ctx)

    def freeze(self) -> dict[str, tuple[object, ...]]:
        return {key: tuple(values) for key, values in self._data.items()}


@dataclass
class Scaffold:
    closers: tuple[str, ...]
    head_expr: list[str] = field(default_factory=list)
    head_stmt: list[str] = field(default_factory=list)
    before: dict[int, list[str]] = field(default_factory=dict)
    after: dict[int, list[str]] = field(default_factory=dict)

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
    prefix: str
    scaffold: Scaffold
    brace_index: dict[int, int]
    brace_order_to_close_idx: dict[int, int]
    tail_text: str
    tail_markers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

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


def _else_if_target(if_node):
    alternative = None
    for field in ("alternative", "else_clause"):
        alternative = if_node.child_by_field_name(field)
        if alternative is not None:
            break
    if alternative is None:
        return None
    if alternative.type == "if_expression":
        return alternative
    if alternative.type != "else_clause":
        return None
    for child in alternative.named_children:
        if child.type == "if_expression":
            return child
    return None


def _tail_if_missing_else(expr_node):
    if expr_node.type != "if_expression":
        return None
    cur = expr_node
    while cur is not None:
        if not has_else_clause(cur):
            return cur
        cur = _else_if_target(cur)
    return None


def classify_block_tail(block_node, *, end_byte: int | None = None) -> TailCompletion:
    tail_node = block_node.named_children[-1] if block_node.named_children else None
    if tail_node is None:
        return TailCompletion(kind=TailCompletionKind.NEEDS_TODO)
    if tail_node.type == "return_expression":
        return TailCompletion(kind=TailCompletionKind.COMPLETE)

    if tail_node.type == "expression_statement":
        expr = tail_node.named_children[0] if tail_node.named_children else None
        if expr is None:
            return TailCompletion(kind=TailCompletionKind.NEEDS_SEMI_TODO)
        if expr.type == "return_expression":
            return TailCompletion(kind=TailCompletionKind.COMPLETE)
        # expression_statement with a `;` child is a real statement (e.g. `foo();`).
        # Without `;`, tree-sitter may wrap a tail expression as expression_statement
        # when parsing scaffolded code - treat it as a value-producing tail.
        has_semicolon = any(c.type == ";" for c in tail_node.children)
        if not has_semicolon:
            if NODE_CLASSIFICATION.get(expr.type) == NodeKind.TAIL_FORWARDING:
                inner = _inner_block_of_wrapper(expr)
                if inner is not None and inner.id != block_node.id:
                    return classify_block_tail(inner, end_byte=end_byte)
            missing_else_if = _tail_if_missing_else(expr)
            if missing_else_if is not None:
                consequence = missing_else_if.child_by_field_name("consequence")
                if consequence is not None:
                    in_consequence = False
                    if end_byte is not None:
                        in_consequence = consequence.start_byte <= end_byte < consequence.end_byte
                    return TailCompletion(
                        kind=TailCompletionKind.IF_MISSING_ELSE,
                        if_consequence_start=consequence.start_byte,
                        if_consequence_end=consequence.end_byte,
                        if_in_consequence=in_consequence,
                    )
                return TailCompletion(kind=TailCompletionKind.NEEDS_SEMI_TODO)
            # Loud-fail policy: downgrade block-yielding tails (must_use
            # warning is visible to oracle, vs silent E0308 from misjudge).
            # Set membership tracks NodeKind, completeness enforced by
            # test_fn_tail_downgrade_set_matches_node_classification.
            # VALUE_WRAPPING (async/try/gen block) intentionally excluded:
            # nightly-only, absent from CodeNet dataset.
            expr_kind = NODE_CLASSIFICATION.get(expr.type)
            if expr_kind in _FN_TAIL_DOWNGRADE_KINDS:
                return TailCompletion(kind=TailCompletionKind.NEEDS_SEMI_TODO)
            return TailCompletion(kind=TailCompletionKind.COMPLETE)
        return TailCompletion(kind=TailCompletionKind.NEEDS_TODO)

    if tail_node.type in {"let_declaration", "empty_statement"}:
        return TailCompletion(kind=TailCompletionKind.NEEDS_TODO)
    if tail_node.type.endswith("_item"):
        return TailCompletion(kind=TailCompletionKind.NEEDS_TODO)
    if tail_node.type == "ERROR":
        return TailCompletion(kind=TailCompletionKind.NEEDS_SEMI_TODO)
    return TailCompletion(kind=TailCompletionKind.COMPLETE)


def block_tail_needs_todo(block_node) -> tuple[bool, bool]:
    """Determine if a block needs a todo!() tail to produce a value.

    Returns (needs_todo, needs_semicolon).
    Shared by FunctionContextRule (function bodies) and MatchContextRule (arm blocks).
    """
    completion = classify_block_tail(block_node)
    if completion.kind == TailCompletionKind.COMPLETE:
        return False, False
    if completion.kind == TailCompletionKind.NEEDS_TODO:
        return True, False
    return True, True
