from __future__ import annotations

from tree_sitter_language_pack import get_language

from c_rust.render.context_rules.base import NODE_CLASSIFICATION


_RUST_LANG = get_language("rust")


def _named_node_types() -> frozenset[str]:
    names: set[str] = set()
    for i in range(_RUST_LANG.node_kind_count):
        if _RUST_LANG.node_kind_is_named(i):
            names.add(_RUST_LANG.node_kind_for_id(i))
    return frozenset(names)


def _expression_subtypes() -> frozenset[str]:
    # Concrete (non-hidden) named subtypes of the `_expression` supertype.
    # `_literal` is itself a supertype - expand it to its concrete subtypes.
    expr_id = None
    literal_id = None
    for super_id in _RUST_LANG.supertypes:
        name = _RUST_LANG.node_kind_for_id(super_id)
        if name == "_expression":
            expr_id = super_id
        elif name == "_literal":
            literal_id = super_id
    assert expr_id is not None, "tree-sitter-rust is missing `_expression` supertype"
    assert literal_id is not None, "tree-sitter-rust is missing `_literal` supertype"

    literal_concrete: set[str] = set()
    for sub_id in _RUST_LANG.subtypes(literal_id):
        literal_concrete.add(_RUST_LANG.node_kind_for_id(sub_id))

    result: set[str] = set()
    for sub_id in _RUST_LANG.subtypes(expr_id):
        name = _RUST_LANG.node_kind_for_id(sub_id)
        if name == "_literal":
            result.update(literal_concrete)
            continue
        # Other hidden supertypes (starting with `_`) are skipped - none expected today.
        if name.startswith("_"):
            continue
        result.add(name)
    return frozenset(result)


# Non-expression node types that appear as ancestors during context analysis and
# therefore must be classified so `find_value_context` can dispatch on them.
REQUIRED_NON_EXPRESSION_ANCESTORS: frozenset[str] = frozenset({
    "let_declaration",
    "arguments",
    "expression_statement",
    "function_item",
    "match_arm",
})


def test_node_classification_covers_all_expression_subtypes() -> None:
    missing = _expression_subtypes() - frozenset(NODE_CLASSIFICATION.keys())
    assert missing == frozenset(), (
        "Unclassified tree-sitter-rust `_expression` subtypes: "
        f"{sorted(missing)}. Add them to NODE_CLASSIFICATION."
    )


def test_node_classification_covers_required_ancestors() -> None:
    missing = REQUIRED_NON_EXPRESSION_ANCESTORS - frozenset(NODE_CLASSIFICATION.keys())
    assert missing == frozenset(), (
        "Unclassified ancestor node types needed by context analysis: "
        f"{sorted(missing)}. Add them to NODE_CLASSIFICATION."
    )


def test_node_classification_has_no_stale_entries() -> None:
    stale = frozenset(NODE_CLASSIFICATION.keys()) - _named_node_types()
    assert stale == frozenset(), (
        "Classified node types not present in tree-sitter-rust grammar: "
        f"{sorted(stale)}. Remove them from NODE_CLASSIFICATION."
    )
