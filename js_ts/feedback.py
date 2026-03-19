from __future__ import annotations

from feedback.language import FeedbackLanguageConfig

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
        "lexical_declaration",
    }),
    function_item_type="function_declaration",
    example_function_wrapper="`function main() { ... }`",
)
