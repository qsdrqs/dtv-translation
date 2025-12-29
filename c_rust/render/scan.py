from __future__ import annotations

from dataclasses import dataclass

_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_CLOSE_TO_OPEN = {")": "(",
    "]": "[",
    "}": "{",
}


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
    ok: bool
    stack: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ClosingResult:
    ok: bool
    suffix: str = ""
    notes: str = ""


@dataclass(frozen=True)
class ClosePlan:
    ok: bool
    stack: tuple[str, ...]
    suffix: str
    closers: tuple[str, ...]
    brace_count: int
    brace_index: dict[int, int]
    brace_order_to_close_idx: dict[int, int]
    notes: str = ""


def _scan_stack(text: str) -> tuple[bool, list[tuple[str, int]], str]:
    in_line_comment = False
    in_block_comment = False
    block_depth = 0
    in_string = False
    string_delim = ""
    escape = False
    stack: list[tuple[str, int]] = []

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
            stack.append((ch, i))
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
