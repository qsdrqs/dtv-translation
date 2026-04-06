from __future__ import annotations

from c_rust.render.scan import closing_suffix as _rust_closing_suffix
from feedback.language import FeedbackLanguageConfig


def _rust_close(text: str) -> str:
    result = _rust_closing_suffix(text)
    return result.suffix if result.ok else ""


RUST_FEEDBACK_LANG = FeedbackLanguageConfig(
    name="Rust",
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
    closing_suffix_fn=_rust_close,
)
