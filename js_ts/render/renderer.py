from __future__ import annotations

from tree_sitter_language_pack import get_parser

from js_ts.render.scan import closing_suffix, scan_unclosed
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

        artifact = Artifact(
            code=code,
            ast_tree=tree,
            sample=self.sample,
            group_events=(),
            group_stack=None,
        )
        return RenderResult(status=RenderStatus.OK, artifact=artifact)
