from __future__ import annotations

from feedback.language import FeedbackLanguageConfig

RUST_FEEDBACK_LANG = FeedbackLanguageConfig(
    name="Rust",
    fence_tags=frozenset({"rust", "rs"}),
    tree_sitter_lang="rust",
    top_level_item_types=frozenset({
        "function_item",
        "const_item",
        "static_item",
        "struct_item",
        "enum_item",
        "union_item",
        "trait_item",
        "impl_item",
        "mod_item",
        "type_item",
        "extern_crate_declaration",
        "use_declaration",
        "macro_definition",
    }),
    function_item_type="function_item",
    example_function_wrapper="`fn main() { ... }`",
)
