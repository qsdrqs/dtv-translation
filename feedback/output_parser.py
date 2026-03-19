from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from tree_sitter_language_pack import SupportedLanguage, get_parser

from core.types import RollbackScope
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
        self._complete = _has_complete_fence(joined)

    @property
    def complete(self) -> bool:
        return self._complete


def _has_complete_fence(text: str) -> bool:
    pos = 0
    while pos < len(text):
        open_idx = text.find("```", pos)
        if open_idx == -1:
            return False
        lang_start = open_idx + 3
        newline_idx = text.find("\n", lang_start)
        if newline_idx == -1:
            return False
        if "`" in text[lang_start:newline_idx]:
            pos = lang_start
            continue
        return text.find("```", newline_idx + 1) != -1
    return False


def parse_feedback_output(
    text: str,
    lang_config: FeedbackLanguageConfig,
) -> ParseResult:
    stripped = text.strip()
    if not stripped:
        return ParseResult(patch=None, error="empty model output", used_fence=False)

    matches = _find_fenced_blocks(stripped)
    if matches:
        if len(matches) > 1:
            return ParseResult(
                patch=None,
                error="multiple fenced code blocks found",
                used_fence=True,
            )
        match = matches[0]
        lang = match.lang.strip().lower()
        if lang not in lang_config.fence_tags:
            return ParseResult(
                patch=None,
                error=f"fenced code block language must be {lang_config.name.lower()}",
                used_fence=True,
            )
        prefix = stripped[: match.start].strip()
        suffix = stripped[match.end :].strip()
        if prefix or suffix:
            return ParseResult(
                patch=None,
                error="fenced output must contain only one code block",
                used_fence=True,
            )
        patch = match.body.strip()
        if not patch:
            return ParseResult(
                patch=None,
                error="empty fenced patch",
                used_fence=True,
            )
        return ParseResult(patch=patch, error=None, used_fence=True)

    if "```" in stripped:
        return ParseResult(
            patch=None,
            error="malformed fenced code block",
            used_fence=True,
        )
    return ParseResult(patch=stripped, error=None, used_fence=False)


def validate_patch_scope(
    patch: str,
    scope: RollbackScope,
    lang_config: FeedbackLanguageConfig,
) -> str | None:
    if scope == RollbackScope.PROGRAM:
        return None

    lang = lang_config.name
    parser = get_parser(cast(SupportedLanguage, lang_config.tree_sitter_lang))
    tree = parser.parse(patch.encode("utf-8"))
    root = tree.root_node
    if root.has_error:
        return f"scope validator: patch is not valid {lang} syntax"

    named_children = [child for child in root.children if child.is_named]
    if not named_children:
        return f"scope validator: patch has no {lang} syntax nodes"

    func_type = lang_config.function_item_type
    top_types = lang_config.top_level_item_types

    if scope == RollbackScope.FUNC:
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

    disallowed = sorted(
        {
            child.type
            for child in named_children
            if child.type in top_types or child.type.endswith("_item")
        }
    )
    if disallowed:
        node_types = ", ".join(disallowed)
        return f"scope validator: {scope.value}-scope patch cannot include top-level items ({node_types})"
    return None
