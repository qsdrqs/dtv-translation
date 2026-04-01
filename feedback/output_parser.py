from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from tree_sitter_language_pack import SupportedLanguage, get_parser

from core.types import Granularity
from feedback.language import FeedbackLanguageConfig


@dataclass(frozen=True)
class _FenceMatch:
    lang: str
    body: str
    start: int
    end: int


def _find_fenced_blocks(text: str) -> list[_FenceMatch]:
    """Find all complete ```lang\\n...``` blocks in *text*."""
    results: list[_FenceMatch] = []
    pos = 0
    while pos < len(text):
        open_idx = text.find("```", pos)
        if open_idx == -1:
            break
        lang_start = open_idx + 3
        newline_idx = text.find("\n", lang_start)
        if newline_idx == -1:
            break
        lang = text[lang_start:newline_idx]
        # Language tag must not contain backticks (e.g. reject ````).
        if "`" in lang:
            pos = lang_start
            continue
        body_start = newline_idx + 1
        close_idx = text.find("```", body_start)
        if close_idx == -1:
            break
        results.append(_FenceMatch(
            lang=lang,
            body=text[body_start:close_idx],
            start=open_idx,
            end=close_idx + 3,
        ))
        pos = close_idx + 3
    return results


@dataclass(frozen=True)
class ParseResult:
    patch: str | None
    error: str | None
    # True when parsing consumed fenced content. False when it fell back to
    # plain, unfenced text.
    used_fence: bool


@dataclass
class FeedbackFenceStreamParser:
    _parts: list[str]
    _complete: bool

    def __init__(self) -> None:
        self._parts = []
        self._complete = False

    def reset(self) -> None:
        self._parts.clear()
        self._complete = False

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        self._parts.append(chunk)
        if self._complete:
            return
        joined = "".join(self._parts)
        self._complete = _has_closing_fence(joined)

    @property
    def complete(self) -> bool:
        return self._complete


def _has_closing_fence(text: str) -> bool:
    for line in text.splitlines():
        if line.rstrip() == "```":
            return True
    return False


def parse_feedback_output(
    text: str,
    lang_config: FeedbackLanguageConfig,
) -> ParseResult:
    stripped = text.strip()
    if not stripped:
        return ParseResult(patch=None, error="empty model output", used_fence=False)
    body, used_fence, error = _extract_complete_fenced_body(
        stripped,
        lang_config=lang_config,
    )
    if error is not None:
        return ParseResult(patch=None, error=error, used_fence=used_fence)
    if body is not None:
        if not body:
            return ParseResult(
                patch=None,
                error="empty fenced patch",
                used_fence=True,
            )
        return ParseResult(patch=body, error=None, used_fence=True)
    if "```" in stripped:
        return ParseResult(
            patch=None,
            error="malformed fenced code block",
            used_fence=True,
        )
    return ParseResult(patch=stripped, error=None, used_fence=False)


def parse_diff_feedback_output(text: str) -> ParseResult:
    stripped = _strip_trailing_fence_close(text.strip())
    if not stripped:
        return ParseResult(patch=None, error="empty model output", used_fence=False)
    body, used_fence, error = _extract_complete_fenced_body(
        stripped,
        lang_config=None,
    )
    if error is not None:
        return ParseResult(patch=None, error=error, used_fence=used_fence)
    if body is not None:
        if not body:
            return ParseResult(
                patch=None,
                error="empty fenced patch",
                used_fence=True,
            )
        return _parse_diff_patch_body(body, used_fence=True)
    open_body, open_error = _extract_open_fence_body(stripped)
    if open_error is not None:
        return ParseResult(patch=None, error=open_error, used_fence=True)
    if open_body is not None:
        if not open_body:
            return ParseResult(patch=None, error="empty fenced patch", used_fence=True)
        return _parse_diff_patch_body(open_body, used_fence=True)
    return _parse_diff_patch_body(stripped, used_fence=False)


def _strip_trailing_fence_close(text: str) -> str:
    lines = text.splitlines()
    while lines and lines[-1].rstrip() == "```":
        lines.pop()
    return "\n".join(lines).strip()


def _extract_complete_fenced_body(
    text: str,
    *,
    lang_config: FeedbackLanguageConfig | None,
) -> tuple[str | None, bool, str | None]:
    matches = _find_fenced_blocks(text)
    if not matches:
        return None, False, None
    if len(matches) > 1:
        return None, True, "multiple fenced code blocks found"
    match = matches[0]
    if lang_config is not None:
        lang = match.lang.strip().lower()
        if lang not in lang_config.fence_tags:
            return None, True, f"fenced code block language must be {lang_config.name.lower()}"
    prefix = text[: match.start].strip()
    if prefix:
        return None, True, "fenced output must contain only one code block"
    return match.body.strip(), True, None


def _extract_open_fence_body(text: str) -> tuple[str | None, str | None]:
    if not text.startswith("```"):
        return None, None
    lang_start = 3
    newline_idx = text.find("\n", lang_start)
    if newline_idx == -1:
        return None, "malformed fenced code block"
    lang = text[lang_start:newline_idx]
    if "`" in lang:
        return None, "malformed fenced code block"
    body = text[newline_idx + 1 :].strip("\n")
    return body, None


def _parse_diff_patch_body(body: str, *, used_fence: bool) -> ParseResult:
    if not _looks_like_diff_patch(body):
        return ParseResult(
            patch=None,
            error="patch must be a unified diff with '+' and '-' lines only",
            used_fence=used_fence,
        )
    replacement_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("+"):
            replacement_lines.append(_strip_diff_prefix(line))
            continue
        if line.startswith("-"):
            continue
        return ParseResult(
            patch=None,
            error="diff patch must contain only '+' and '-' lines",
            used_fence=used_fence,
        )
    if not replacement_lines:
        return ParseResult(
            patch=None,
            error="diff patch must contain at least one '+' line",
            used_fence=used_fence,
        )
    patch = "\n".join(replacement_lines).strip()
    if not patch:
        return ParseResult(patch=None, error="empty diff replacement", used_fence=used_fence)
    return ParseResult(patch=patch, error=None, used_fence=used_fence)


def _looks_like_diff_patch(text: str) -> bool:
    saw_prefixed = False
    for line in text.splitlines():
        if not line:
            return False
        if line.startswith("+") or line.startswith("-"):
            saw_prefixed = True
            continue
        return False
    return saw_prefixed


def _strip_diff_prefix(line: str) -> str:
    if line.startswith("+ "):
        return line[2:]
    return line[1:]


def snippet_contains_function(
    snippet: str,
    lang_config: FeedbackLanguageConfig,
) -> bool:
    """Check whether *snippet* contains a function declaration/item.

    The snippet may be incomplete (e.g. a function header + first statement
    without a closing brace).  The renderer's ``closing_suffix_fn`` is used
    to close the code so that tree-sitter can identify the function node.
    """
    suffix = lang_config.closing_suffix_fn(snippet)
    closed = snippet + suffix
    parser = get_parser(cast(SupportedLanguage, lang_config.tree_sitter_lang))
    tree = parser.parse(closed.encode("utf-8"))
    root = tree.root_node
    func_type = lang_config.function_item_type
    return any(
        child.type == func_type
        for child in root.children
        if child.is_named
    )


def validate_patch_scope(
    patch: str,
    scope: Granularity,
    lang_config: FeedbackLanguageConfig,
    *,
    rollback_snippet: str | None = None,
) -> str | None:
    if scope == Granularity.PROGRAM:
        return None

    lang = lang_config.name
    patch_suffix = lang_config.closing_suffix_fn(patch)
    parser = get_parser(cast(SupportedLanguage, lang_config.tree_sitter_lang))
    tree = parser.parse((patch + patch_suffix).encode("utf-8"))
    root = tree.root_node
    if root.has_error:
        # Continuation clauses (catch, else, finally, ...) cannot be parsed
        # in isolation by tree-sitter.  If the rollback snippet suffers the
        # same parse error, the error comes from the surrounding context, not
        # from the patch itself.  Skip all AST-based checks in that case.
        if rollback_snippet is not None:
            rb_suffix = lang_config.closing_suffix_fn(rollback_snippet)
            rb_tree = parser.parse((rollback_snippet + rb_suffix).encode("utf-8"))
            if rb_tree.root_node.has_error:
                return None
        return f"scope validator: patch is not valid {lang} syntax"

    named_children = [child for child in root.children if child.is_named]
    if not named_children:
        return f"scope validator: patch has no {lang} syntax nodes"

    func_type = lang_config.function_item_type
    top_types = lang_config.top_level_item_types

    if scope == Granularity.FUNC:
        non_func_top = sorted(
            {
                child.type
                for child in named_children
                if (child.type in top_types or child.type.endswith("_item"))
                and child.type != func_type
            }
        )
        if non_func_top:
            node_types = ", ".join(non_func_top)
            return (
                f"scope validator: func-scope patch cannot include"
                f" non-function top-level items ({node_types})"
            )
        return None

    # STMT / BLOCK scope.
    # When the rollback snippet itself contains a function header (e.g. the
    # first checkpoint bundles "function header + 1st statement"), the model
    # must include the function header in its repair patch.  Allow the
    # function item type in that case.
    allowed_in_stmt: set[str] = set()
    rollback_suffix = None
    if (
        scope == Granularity.STMT
        and rollback_snippet is not None
        and snippet_contains_function(rollback_snippet, lang_config)
    ):
        rollback_suffix = lang_config.closing_suffix_fn(rollback_snippet)
        # Compare renderer closing suffixes, not just a closed/open boolean.
        # The suffix is the exact structural boundary the prefix still owes.
        # Keeping it identical is sufficient for this special case: it allows
        # a legal incomplete first-stmt repair prefix, but rejects repairs that
        # close the function/block early or open extra structure.
        if patch_suffix != rollback_suffix:
            return (
                "scope validator: stmt-scope patch must preserve the rollback"
                " prefix boundary"
            )
        allowed_in_stmt.add(func_type)

    disallowed = sorted(
        {
            child.type
            for child in named_children
            if (child.type in top_types or child.type.endswith("_item"))
            and child.type not in allowed_in_stmt
        }
    )
    if disallowed:
        node_types = ", ".join(disallowed)
        return f"scope validator: {scope.value}-scope patch cannot include top-level items ({node_types})"
    return None
