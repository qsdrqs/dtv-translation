from __future__ import annotations

from dataclasses import dataclass

_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_CLOSE_TO_OPEN = {v: k for k, v in _OPEN_TO_CLOSE.items()}


def _looks_like_char_literal(text: str, idx: int) -> bool:
    # Heuristic to avoid treating Rust lifetimes like strings.
    n = len(text)
    j = idx + 1
    escaped = False
    while j < n and (j - idx) <= 6:
        ch = text[j]
        if escaped:
            escaped = False
        else:
            if ch == "\\":
                escaped = True
            elif ch == "'":
                return True
            elif ch.isspace():
                return False
        j += 1
    return False


@dataclass(frozen=True)
class ScanOutcome:
    """Result of scanning for unclosed delimiters."""
    ok: bool
    stack: tuple[str, ...] = ()  # Unclosed opener stack (outer -> inner).
    notes: str = ""  # Reason for failure if ok is False.


@dataclass(frozen=True)
class ClosingResult:
    """Suggested closing suffix for a prefix."""
    ok: bool
    suffix: str = ""  # Closing delimiters to append.
    notes: str = ""  # Reason for failure if ok is False.


@dataclass(frozen=True)
class ClosePlan:
    """Detailed plan for closing delimiters and brace tracking."""
    ok: bool
    stack: tuple[str, ...]  # Unclosed opener stack (outer -> inner).
    suffix: str  # Closing suffix to append.
    closers: tuple[str, ...]  # Close tokens in append order.
    brace_count: int  # Number of unmatched "{" entries.
    brace_index: dict[int, int]  # Map: brace byte index -> nesting order.
    brace_order_to_close_idx: dict[int, int]  # Map: brace order -> closers index.
    notes: str = ""  # Reason for failure if ok is False.


def _scan_stack(text: str) -> tuple[bool, list[tuple[str, int]], str]:
    in_line_comment = False
    in_block_comment = False
    block_depth = 0
    in_string = False
    string_delim = ""
    escape = False
    stack: list[tuple[str, int]] = []

    # Pre-compute char index -> UTF-8 byte offset mapping so that
    # brace positions align with tree-sitter byte offsets (which use
    # UTF-8 byte counts, not Python character counts).
    char_to_byte: list[int] = []
    byte_pos = 0
    for ch in text:
        char_to_byte.append(byte_pos)
        byte_pos += len(ch.encode("utf-8"))

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                i += 2
                if block_depth <= 0:
                    in_block_comment = False
                continue
            i += 1
            continue

        if in_string:
            if escape:
                escape = False
                i += 1
                continue
            if ch == "\\":
                escape = True
                i += 1
                continue
            if ch == string_delim:
                in_string = False
                string_delim = ""
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            block_depth = 1
            i += 2
            continue

        if ch == "\"":
            in_string = True
            string_delim = ch
            i += 1
            continue
        if ch == "'":
            if _looks_like_char_literal(text, i):
                in_string = True
                string_delim = ch
                i += 1
                continue

        if ch in _OPEN_TO_CLOSE:
            stack.append((ch, char_to_byte[i]))
            i += 1
            continue
        if ch in _CLOSE_TO_OPEN:
            if stack and stack[-1][0] == _CLOSE_TO_OPEN[ch]:
                stack.pop()
            i += 1
            continue

        i += 1

    if in_string:
        return False, [], "render_continue:unterminated_string"
    if in_block_comment or in_line_comment:
        return False, [], "render_continue:unterminated_comment"

    return True, stack, ""


def scan_unclosed(text: str) -> ScanOutcome:
    ok, stack, notes = _scan_stack(text)
    if not ok:
        return ScanOutcome(ok=False, notes=notes)
    return ScanOutcome(ok=True, stack=tuple(ch for ch, _ in stack))


def closing_suffix(text: str) -> ClosingResult:
    ok, stack, notes = _scan_stack(text)
    if not ok:
        return ClosingResult(ok=False, notes=notes)
    closers = "".join(_OPEN_TO_CLOSE[ch] for ch, _ in reversed(stack))
    return ClosingResult(ok=True, suffix=closers)


def brace_close_plan(text: str) -> ClosePlan:
    ok, stack_entries, notes = _scan_stack(text)
    if not ok:
        return ClosePlan(
            ok=False,
            stack=(),
            suffix="",
            closers=(),
            brace_count=0,
            brace_index={},
            brace_order_to_close_idx={},
            notes=notes,
        )

    stack = tuple(ch for ch, _ in stack_entries)
    closers_list = [_OPEN_TO_CLOSE[ch] for ch, _ in reversed(stack_entries)]

    brace_stack_indices = [idx for idx, (ch, _) in enumerate(stack_entries) if ch == "{"]
    brace_stack_indices_rev = list(reversed(brace_stack_indices))
    brace_index = {
        stack_entries[stack_idx][1]: order for order, stack_idx in enumerate(brace_stack_indices_rev)
    }
    brace_order_to_close_idx = {}
    for order, stack_idx in enumerate(brace_stack_indices_rev):
        close_idx = len(stack_entries) - 1 - stack_idx
        brace_order_to_close_idx[order] = close_idx

    return ClosePlan(
        ok=True,
        stack=stack,
        suffix="".join(closers_list),
        closers=tuple(closers_list),
        brace_count=len(brace_stack_indices),
        brace_index=brace_index,
        brace_order_to_close_idx=brace_order_to_close_idx,
        notes="",
    )
