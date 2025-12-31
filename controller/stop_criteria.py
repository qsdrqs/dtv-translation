from __future__ import annotations

from dataclasses import dataclass

from transformers import StoppingCriteria


@dataclass(frozen=True)
class LanguageProfile:
    """Delimiters used to identify strings and comments for a language."""
    line_comment_starts: tuple[str, ...]
    block_comment_pairs: tuple[tuple[str, str], ...]
    string_delims: tuple[str, ...]  # Quote characters treated as string delimiters.


RUST_PROFILE = LanguageProfile(
    line_comment_starts=("//",),
    block_comment_pairs=(("/*", "*/"),),
    string_delims=('"', "'"),
)

TS_PROFILE = LanguageProfile(
    line_comment_starts=("//",),
    block_comment_pairs=(("/*", "*/"),),
    string_delims=('"', "'", "`"),
)


def _scan_string_comment_state(text: str, profile: LanguageProfile) -> dict[str, bool]:
    in_line_comment = False
    in_block_comment = False
    in_string = False
    string_delim = ""
    escape = False
    block_end = ""

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        two = ch + nxt

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if block_end and text.startswith(block_end, i):
                in_block_comment = False
                i += len(block_end)
            else:
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

        if two in profile.line_comment_starts:
            in_line_comment = True
            i += 2
            continue

        for start, end in profile.block_comment_pairs:
            if text.startswith(start, i):
                in_block_comment = True
                block_end = end
                i += len(start)
                break
        if in_block_comment:
            continue

        if ch in profile.string_delims:
            in_string = True
            string_delim = ch
            i += 1
            continue

        i += 1

    return {
        "in_string": in_string,
        "in_line_comment": in_line_comment,
        "in_block_comment": in_block_comment,
    }


class DTVStoppingCriteria(StoppingCriteria):
    def __init__(self, tokenizer, language_profile: LanguageProfile) -> None:
        self.tokenizer = tokenizer
        self.language_profile = language_profile

    def __call__(self, input_ids, scores, **kwargs) -> bool:
        decoded = self.tokenizer.decode(input_ids[0], skip_special_tokens=True)
        stripped = decoded.rstrip()
        if not stripped:
            return False

        last_char = stripped[-1]
        if last_char not in {";", "}"}:
            return False

        state = _scan_string_comment_state(stripped, self.language_profile)
        if state["in_string"] or state["in_line_comment"] or state["in_block_comment"]:
            return False

        # TODO: bracket/brace depth tracking to avoid stopping mid-block context.
        # TODO: raw strings (Rust) and template literals (TS) are not handled here.
        return True
