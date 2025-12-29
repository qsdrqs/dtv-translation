from __future__ import annotations

from tree_sitter_language_pack import get_parser

from c_rust.render.context_rules import Analysis, CONTEXT_RULES, ContextRegistry

_PARSER = get_parser("rust")


def _get_parser():
    return _PARSER


def analyze_prefix(prefix: str, *, parse_input: str | None = None) -> Analysis:
    parser = _get_parser()

    stripped = prefix.rstrip()
    if not stripped:
        return Analysis(ok=False, notes="render_continue:empty")

    # Parse the scaffolded input, but anchor analysis to the last non-whitespace byte
    # of the original prefix. This keeps suffix-only reasoning intact.
    parse_text = parse_input if parse_input is not None else prefix
    parse_bytes = parse_text.encode("utf-8")
    end_byte = len(stripped.encode("utf-8"))
    tree = parser.parse(parse_bytes)
    if end_byte == 0:
        return Analysis(ok=False, notes="render_continue:empty")

    # Find the smallest node covering the end of the prefix; this is our context anchor.
    anchor = tree.root_node.descendant_for_byte_range(max(end_byte - 1, 0), end_byte)
    if anchor is None:
        return Analysis(ok=False, notes="render_continue:no_anchor")

    # Walk up the tree to identify enclosing constructs that drive suffix decisions.
    # Each rule is responsible for a distinct construct and updates shared flags.
    registry = ContextRegistry()
    for rule in CONTEXT_RULES:
        nodes = rule.find_nodes(anchor)
        rule.apply_analysis(nodes, anchor=anchor, end_byte=end_byte, prefix_bytes=parse_bytes, registry=registry)

    return Analysis(
        ok=True,
        notes="",
        end_byte=end_byte,
        contexts=registry.freeze(),
    )
