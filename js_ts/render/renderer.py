from __future__ import annotations

from tree_sitter_language_pack import get_parser

from js_ts.render.scan import closing_suffix, scan_unclosed
from js_ts.render.context_rules import apply_context_rules
from js_ts.render.groups import ts_group_stack
from core.types import Artifact, RenderResult, RenderStatus, TranslationSample

_TS_PARSER = get_parser("typescript")


def _parse_ts(code: str):
    return _TS_PARSER.parse(code.encode("utf-8"))


class JSToTSRenderer:
    def __init__(self, sample: TranslationSample | None = None) -> None:
        self.sample = sample

    def try_render(self, prefix: str) -> RenderResult:
        try:
            return self._try_render(prefix)
        except Exception as exc:  # pragma: no cover - defensive
            return RenderResult(
                status=RenderStatus.FAIL,
                artifact=None,
                notes=f"render_fail:{exc.__class__.__name__}",
            )

    def _try_render(self, prefix: str) -> RenderResult:
        if not prefix.strip():
            return RenderResult(status=RenderStatus.CONTINUE, notes="render_continue:empty")

        scan = scan_unclosed(prefix)
        if not scan.ok:
            return RenderResult(status=RenderStatus.CONTINUE, notes=scan.notes)

        if any(ch in {"(", "["} for ch in scan.stack):
            # NOTE: may fail for valid stmts inside unclosed parens/brackets,
            # but those are rare and we can improve later if needed.
            return RenderResult(
                status=RenderStatus.CONTINUE,
                notes="render_continue:unclosed_paren_bracket",
            )

        result = closing_suffix(prefix)
        if not result.ok:
            return RenderResult(status=RenderStatus.CONTINUE, notes=result.notes)

        code = prefix + result.suffix
        tree = _parse_ts(code)

        prefix_byte_len = len(prefix.encode("utf-8"))
        patched = apply_context_rules(code, prefix_byte_len, tree)
        if patched != code:
            code = patched
            tree = _parse_ts(code)

        if not _has_module_semantics(tree):
            code = code + "\nexport {};"
            tree = _parse_ts(code)

        if _cursor_needs_continuation(tree, prefix_end_byte=prefix_byte_len):
            return RenderResult(
                status=RenderStatus.CONTINUE,
                notes="render_continue:cursor_incomplete",
            )

        source_bytes = code.encode("utf-8")
        group_stack = ts_group_stack(
            tree,
            prefix_end_byte=prefix_byte_len,
            source_bytes=source_bytes,
        )

        artifact = Artifact(
            code=code,
            ast_tree=tree,
            sample=self.sample,
            group_events=(),
            group_stack=group_stack,
        )
        return RenderResult(status=RenderStatus.OK, artifact=artifact)


def _has_module_semantics(tree) -> bool:
    for child in tree.root_node.children:
        if child.type in {"import_statement", "export_statement"}:
            return True
    return False


def _cursor_needs_continuation(tree, *, prefix_end_byte: int) -> bool:
    for node in _walk_nodes(tree.root_node):
        if node.is_missing and node.start_byte == prefix_end_byte:
            return True
        if node.type == "ERROR" and node.start_byte <= prefix_end_byte <= node.end_byte:
            return True
    return False


def _walk_nodes(root):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        children = node.children
        if children:
            stack.extend(reversed(children))
