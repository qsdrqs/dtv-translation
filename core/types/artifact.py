from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Tree

from .diff_testing import TranslationSample
from .enums import Granularity, GroupEventAction, RenderStatus


@dataclass(frozen=True)
class GroupStackFrame:
    kind: Granularity
    name_id: str | None = None
    group_id: str | None = None
    start_stmt: int | None = None

    @staticmethod
    def matches(previous_frame: GroupStackFrame, current_frame: GroupStackFrame) -> bool:
        if previous_frame.kind != current_frame.kind:
            return False
        if (
            previous_frame.group_id is not None
            and current_frame.group_id is not None
            and previous_frame.group_id != current_frame.group_id
        ):
            return False
        if (
            previous_frame.name_id is not None
            and current_frame.name_id is not None
            and previous_frame.name_id != current_frame.name_id
        ):
            return False
        return True


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
