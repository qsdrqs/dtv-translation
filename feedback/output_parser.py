from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from tree_sitter_language_pack import SupportedLanguage, get_parser

from core.llm_output import DEFAULT_WRITE_REGION_MARKERS, WriteRegionMarkers
from core.types import Granularity
from feedback.language import FeedbackLanguageConfig


@dataclass(frozen=True)
class ParseResult:
    patch: str | None
    error: str | None
    used_write_region: bool


@dataclass
class FeedbackWriteRegionStreamParser:
    _parts: list[str]
    _complete: bool
    _markers: WriteRegionMarkers

    def __init__(self, markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS) -> None:
        self._parts = []
        self._complete = False
        self._markers = markers

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
        self._complete = _has_end_marker(joined, self._markers)

    @property
    def complete(self) -> bool:
        return self._complete


def _has_end_marker(text: str, markers: WriteRegionMarkers) -> bool:
    for line in text.splitlines():
        if line.strip() == markers.end_marker:
            return True
    return False


def parse_feedback_output(
    text: str,
    lang_config: FeedbackLanguageConfig,
    *,
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
) -> ParseResult:
    _ = lang_config
    return _parse_single_write_region(text, markers=markers)


def parse_diff_feedback_output(
    text: str,
    *,
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
) -> ParseResult:
    region = _parse_single_write_region(text, markers=markers)
    if region.error is not None or region.patch is None:
        return region
    return _parse_diff_patch_body(region.patch, used_write_region=True)


def _parse_single_write_region(
    text: str,
    *,
    markers: WriteRegionMarkers,
) -> ParseResult:
    if not text.strip():
        return ParseResult(patch=None, error="empty model output", used_write_region=False)

    lines = text.splitlines(keepends=True)
    outside_before: list[str] = []
    outside_after: list[str] = []
    body_parts: list[str] = []
    saw_begin = False
    saw_end = False
    inside = False

    for line in lines:
        stripped = line.strip()
        if not inside:
            if stripped == markers.begin_marker:
                if saw_begin:
                    return ParseResult(
                        patch=None,
                        error="multiple write regions found",
                        used_write_region=True,
                    )
                saw_begin = True
                inside = True
                continue
            if saw_end:
                outside_after.append(line)
            else:
                outside_before.append(line)
            continue

        if stripped == markers.end_marker:
            inside = False
            saw_end = True
            continue
        if stripped.startswith("```"):
            return ParseResult(
                patch=None,
                error="write region must contain raw code only",
                used_write_region=True,
            )
        body_parts.append(line)

    if inside:
        return ParseResult(
            patch=None,
            error="unterminated write region",
            used_write_region=True,
        )
    if not saw_begin:
        return ParseResult(
            patch=None,
            error="missing write region",
            used_write_region=False,
        )
    if not saw_end:
        return ParseResult(
            patch=None,
            error="unterminated write region",
            used_write_region=True,
        )
    if "".join(outside_before).strip() or "".join(outside_after).strip():
        return ParseResult(
            patch=None,
            error="write-region output must contain exactly one write region",
            used_write_region=True,
        )

    body = "".join(body_parts).strip("\n")
    if not body:
        return ParseResult(
            patch=None,
            error="empty write region",
            used_write_region=True,
        )
    return ParseResult(patch=body, error=None, used_write_region=True)


def _parse_diff_patch_body(body: str, *, used_write_region: bool) -> ParseResult:
    if not _looks_like_diff_patch(body):
        return ParseResult(
            patch=None,
            error="patch must be a unified diff with '+' and '-' lines only",
            used_write_region=used_write_region,
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
            used_write_region=used_write_region,
        )
    if not replacement_lines:
        return ParseResult(
            patch=None,
            error="diff patch must contain at least one '+' line",
            used_write_region=used_write_region,
        )
    patch = "\n".join(replacement_lines).strip()
    if not patch:
        return ParseResult(
            patch=None,
            error="empty diff replacement",
            used_write_region=used_write_region,
        )
    return ParseResult(patch=patch, error=None, used_write_region=used_write_region)


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

    allowed_in_stmt: set[str] = set()
    rollback_suffix = None
    if (
        scope == Granularity.STMT
        and rollback_snippet is not None
        and snippet_contains_function(rollback_snippet, lang_config)
    ):
        rollback_suffix = lang_config.closing_suffix_fn(rollback_snippet)
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
