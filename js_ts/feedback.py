from __future__ import annotations

from feedback.language import FeedbackLanguageConfig
from js_ts.render.scan import closing_suffix as _ts_closing_suffix


def _ts_close(text: str) -> str:
    result = _ts_closing_suffix(text)
    return result.suffix if result.ok else ""


TS_FEEDBACK_LANG = FeedbackLanguageConfig(
    name="TypeScript",
    fence_tags=frozenset({"typescript", "ts"}),
    tree_sitter_lang="typescript",
    top_level_item_types=frozenset({
        "function_declaration",
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "import_statement",
        "export_statement",
    }),
    function_item_type="function_declaration",
    example_function_wrapper="`function main() { ... }`",
    closing_suffix_fn=_ts_close,
)
