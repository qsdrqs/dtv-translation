from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedbackLanguageConfig:
    name: str
    fence_tags: frozenset[str]
    tree_sitter_lang: str
    top_level_item_types: frozenset[str]
    function_item_type: str
    example_function_wrapper: str
