from __future__ import annotations

import pytest

from core.llm_output import FenceParser, FenceReopenError, FenceState


def test_parser_tracks_inside_and_output() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    delta = parser.feed("preamble;\n")
    assert parser.state == FenceState.OUTSIDE
    assert delta.pre_fence == "preamble;\n"
    assert parser.consume_inside() == ""

    delta = parser.feed("```rust\n")
    assert parser.state == FenceState.INSIDE
    assert delta.fence_lang == "rust"

    delta = parser.feed("let x = 1;\n")
    assert delta.code == "let x = 1;\n"
    assert parser.consume_inside() == "let x = 1;\n"
    assert parser.consume_inside() == ""

    delta = parser.feed("```\n")
    assert parser.state == FenceState.DONE

    delta = parser.feed("after\n")
    assert delta.post_fence == "after\n"


def test_parser_split_fence_tokens() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    parser.feed("`")
    parser.feed("``ru")
    delta = parser.feed("st\ncode")
    assert delta.code == "code"
    assert parser.consume_inside() == "code"


def test_parser_pending_text_outside_buffered() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    delta = parser.feed("``")
    assert delta.pending_text == "``"
    assert delta.pre_fence == ""
    assert delta.fence_state == FenceState.OUTSIDE

    delta = parser.feed("`rust\ncode")
    assert delta.fence_lang == "rust"
    assert delta.code == "code"
    assert delta.pending_text == ""
    assert parser.consume_inside() == "code"


def test_parser_pending_text_inside_closing() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    parser.feed("```rust\nline\n")
    delta = parser.feed("```")
    assert delta.pending_text == "```"
    assert delta.fence_state == FenceState.INSIDE

    delta = parser.feed("\n")
    assert delta.fence_state == FenceState.DONE
    assert delta.pending_text == ""


def test_parser_pending_text_render_snapshot() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    delta = parser.feed("""```rust
code
``""")
    assert delta.pending_text == "``"
    assert delta.render() == """```rust
code
``"""


def test_parser_non_rust_fence_ignored() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    delta = parser.feed("""```python
print('x')
```
""")
    assert parser.state == FenceState.OUTSIDE
    assert delta.pre_fence == """```python
print('x')
```
"""
    assert parser.consume_inside() == ""


@pytest.mark.parametrize(
    "initial_state",
    [FenceState.OUTSIDE, FenceState.INSIDE, FenceState.DONE],
)
def test_feed_empty_preserves_fence_state(initial_state: FenceState) -> None:
    """feed('') must return fence_state=self.state, not default OUTSIDE."""
    parser = FenceParser(allowed_langs=("rust", "rs"))
    if initial_state == FenceState.INSIDE:
        parser.feed("```rust\n")
    elif initial_state == FenceState.DONE:
        parser.feed("```rust\n")
        parser.feed("```\n")
    assert parser.state == initial_state

    result = parser.feed("")
    assert result.fence_state == initial_state
    assert parser.state == initial_state


def test_parser_reopen_skips_marker() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    parser.feed("```rust\n")
    parser.feed("line1\n")
    result = parser.feed("```rust\nline2\n")
    # Reopen marker is skipped; parser stays INSIDE and extracts new code
    assert parser.state == FenceState.INSIDE
    assert result.code == "line2\n"
    # Old code is still in inside_parts
    assert parser.consume_inside() == "line1\nline2\n"
