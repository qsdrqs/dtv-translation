from __future__ import annotations

from dataclasses import dataclass

_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_CLOSE_TO_OPEN = {v: k for k, v in _OPEN_TO_CLOSE.items()}


@dataclass(frozen=True)
class ScanOutcome:
    """Result of scanning for unclosed delimiters."""
    ok: bool
    stack: tuple[str, ...] = ()  # Unclosed opener stack (outer -> inner).
    notes: str = ""


@dataclass(frozen=True)
class ClosingResult:
    """Suggested closing suffix for a prefix."""
    ok: bool
    suffix: str = ""
    notes: str = ""


@dataclass
class _StackEntry:
    opener: str
    index: int
    template_expr: bool = False  # True if this { came from a template literal ${.


def _scan_stack(text: str) -> tuple[bool, list[_StackEntry], str]:
    in_line_comment = False
    in_block_comment = False
    in_string = False
    string_delim = ""
    escape = False
    # mode_stack: "code" (normal) or "template" (inside backtick literal).
    # ${ in template pushes "code"; matching } pops back to "template".
    mode_stack: list[str] = ["code"]
    stack: list[_StackEntry] = []

    i = 0
    n = len(text)
    while i < n:
        mode = mode_stack[-1]
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        # template literal content
        if mode == "template":
            if escape:
                escape = False
                i += 1
                continue
            if ch == "\\":
                escape = True
                i += 1
                continue
            if ch == "`":
                mode_stack.pop()
                i += 1
                continue
            if ch == "$" and nxt == "{":
                stack.append(_StackEntry("{", i + 1, template_expr=True))
                mode_stack.append("code")
                i += 2
                continue
            i += 1
            continue

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # Block comments do NOT nest in JS/TS (unlike Rust).
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
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
            i += 2
            continue

        if ch == '"' or ch == "'":
            in_string = True
            string_delim = ch
            i += 1
            continue

        if ch == "`":
            mode_stack.append("template")
            i += 1
            continue

        if ch in _OPEN_TO_CLOSE:
            stack.append(_StackEntry(ch, i))
            i += 1
            continue

        if ch in _CLOSE_TO_OPEN:
            expected = _CLOSE_TO_OPEN[ch]
            if stack and stack[-1].opener == expected:
                entry = stack.pop()
                if entry.template_expr:
                    mode_stack.pop()
            i += 1
            continue

        i += 1

    if in_string:
        return False, [], "render_continue:unterminated_string"
    if in_block_comment or in_line_comment:
        return False, [], "render_continue:unterminated_comment"
    if any(m == "template" for m in mode_stack):
        return False, [], "render_continue:unterminated_template"

    return True, stack, ""


def scan_unclosed(text: str) -> ScanOutcome:
    ok, stack, notes = _scan_stack(text)
    if not ok:
        return ScanOutcome(ok=False, notes=notes)
    return ScanOutcome(ok=True, stack=tuple(e.opener for e in stack))


def closing_suffix(text: str) -> ClosingResult:
    ok, stack, notes = _scan_stack(text)
    if not ok:
        return ClosingResult(ok=False, notes=notes)
    closers = "".join(_OPEN_TO_CLOSE[e.opener] for e in reversed(stack))
    return ClosingResult(ok=True, suffix=closers)
