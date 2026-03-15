from __future__ import annotations

from tree_sitter_language_pack import get_parser

from js_ts.render.context_rules.try_catch_rule import apply_try_catch
from js_ts.render.context_rules.function_return_rule import apply_function_return

_TS_PARSER = get_parser("typescript")


def apply_context_rules(code: str, prefix_len: int, tree) -> str:
    source_bytes = code.encode("utf-8")

    new_code = apply_try_catch(code, prefix_len, tree, source_bytes)
    if new_code != code:
        code = new_code
        source_bytes = code.encode("utf-8")
        tree = _TS_PARSER.parse(source_bytes)

    code = apply_function_return(code, prefix_len, tree, source_bytes)
    return code


__all__ = ["apply_context_rules"]
