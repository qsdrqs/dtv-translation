from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class PatchPhase(str, Enum):
    SYNTAX = "syntax"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class Analysis:
    ok: bool
    notes: str = ""
    end_byte: int = 0
    contexts: dict[str, tuple[object, ...]] = field(default_factory=dict)

    def get(self, key: str) -> tuple[object, ...]:
        return self.contexts.get(key, ())


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


def block_tail_needs_todo(block_node) -> tuple[bool, bool]:
    """Determine if a block needs a todo!() tail to produce a value.

    Returns (needs_todo, needs_semicolon).
    Shared by FunctionContextRule (function bodies) and MatchContextRule (arm blocks).
    """
    tail_node = block_node.named_children[-1] if block_node.named_children else None
    if tail_node is None:
        return True, False
    if tail_node.type == "return_expression":
        return False, False
    if tail_node.type == "expression_statement":
        expr = tail_node.named_children[0] if tail_node.named_children else None
        if expr is None:
            return True, True
        if expr.type == "return_expression":
            return False, False
        # expression_statement with a `;` child is a real statement (e.g. `foo();`).
        # Without `;`, tree-sitter may wrap a tail expression as expression_statement
        # when parsing scaffolded code - treat it as a value-producing tail.
        has_semicolon = any(c.type == ";" for c in tail_node.children)
        if not has_semicolon:
            if expr.type == "if_expression" and not has_else_clause(expr):
                return True, True
            if expr.type in {"while_expression", "for_expression"}:
                return True, True
            return False, False
        return True, False
    if tail_node.type in {"let_declaration", "let_statement", "empty_statement"}:
        return True, False
    if tail_node.type.endswith("_item") or tail_node.type == "ERROR":
        return True, tail_node.type == "ERROR"
    return False, False
