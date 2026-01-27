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


def test_parser_reopen_raises() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    parser.feed("```rust\n")
    parser.feed("line1\n")
    with pytest.raises(FenceReopenError):
        parser.feed("```rust\n")
