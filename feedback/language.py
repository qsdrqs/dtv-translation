from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


def _noop_closing_suffix(_text: str) -> str:
    raise NotImplementedError("closing_suffix_fn not configured for this language")


@dataclass(frozen=True)
class FeedbackLanguageConfig:
    name: str
    tree_sitter_lang: str
    top_level_item_types: frozenset[str]
    function_item_type: str
    example_function_wrapper: str
    closing_suffix_fn: Callable[[str], str] = field(default=_noop_closing_suffix)
    comment_prefix: str = "//"
