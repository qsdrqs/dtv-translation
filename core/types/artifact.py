from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Tree

from .diff_testing import TranslationSample
from .enums import Granularity, GroupEventAction, RenderStatus


@dataclass(frozen=True)
class GroupStackFrame:
    kind: Granularity
    name_id: str | None = None


@dataclass(frozen=True)
class GroupEvent:
    action: GroupEventAction
    kind: Granularity


@dataclass(frozen=True)
class Artifact:
    code: str
    ast_tree: Tree | None = None
    sample: TranslationSample | None = None
    group_events: tuple[GroupEvent, ...] = ()
    group_stack: tuple[GroupStackFrame, ...] | None = None


@dataclass(frozen=True)
class RenderResult:
    status: RenderStatus
    artifact: Artifact | None = None
    notes: str = ""
