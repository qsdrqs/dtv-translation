from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.analyze import analyze_prefix
from c_rust.render.context_rules import PatchPhase, apply_patch_rules
from c_rust.render.groups import parse_rust, rust_group_stack
from c_rust.render.scan import brace_close_plan, scan_unclosed
from c_rust.render.suffix import create_plan, plan_to_suffix
from core.types import Artifact, RenderResult, RenderStatus, TranslationSample


@dataclass(frozen=True)
class RenderConfig:
    """Configuration for the C to Rust renderer."""
    allow_continue_on_error: bool = True  # Continue instead of failing on errors.


class CRustRenderer:
    def __init__(
        self,
        config: RenderConfig | None = None,
        sample: TranslationSample | None = None,
    ) -> None:
        self.config = config or RenderConfig()
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

        close_plan = brace_close_plan(prefix)
        if not close_plan.ok:
            return RenderResult(status=RenderStatus.CONTINUE, notes=close_plan.notes)
        if any(ch in {"(", "["} for ch in close_plan.stack):
            # NOTE: May fail for valid stmts that inside of unclosed parens/brackets,
            # but those are rare and we can improve later if needed.
            return RenderResult(status=RenderStatus.CONTINUE, notes="render_continue:unclosed_paren_bracket")

        plan = create_plan(prefix, close_plan)
        for phase in (PatchPhase.SYNTAX, PatchPhase.SEMANTIC):
            analysis = analyze_prefix(prefix, parse_input=prefix + plan.render())
            if not analysis.ok:
                return RenderResult(status=RenderStatus.CONTINUE, notes=analysis.notes)
            apply_patch_rules(plan, analysis, phases=(phase,))

        suffix = plan_to_suffix(plan)
        if not suffix.ok:
            return RenderResult(status=RenderStatus.CONTINUE, notes=suffix.notes)

        code = prefix + suffix.content
        end_byte = len(prefix.rstrip().encode("utf-8"))
        tree = parse_rust(code)
        if _cursor_needs_continuation(tree, prefix_end_byte=end_byte):
            return RenderResult(
                status=RenderStatus.CONTINUE,
                notes=_with_note(suffix.notes, "render_continue:cursor_incomplete"),
            )
        group_stack = rust_group_stack(
            tree,
            prefix_end_byte=end_byte,
            source_bytes=code.encode("utf-8"),
            skip_function_body_block=True,
        )
        artifact = Artifact(
            code=code,
            ast_tree=tree,
            sample=self.sample,
            group_events=(),
            group_stack=group_stack,
        )
        return RenderResult(status=RenderStatus.OK, artifact=artifact, notes=suffix.notes)


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


def _with_note(notes: str, extra: str) -> str:
    if notes:
        return f"{notes},{extra}"
    return extra
