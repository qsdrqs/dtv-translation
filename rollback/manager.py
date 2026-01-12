from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from core.types import Granularity, GroupEvent, GroupEventAction, RollbackScope


@dataclass
class Checkpoint:
    """Snapshot of the prefix after a committed statement."""
    prefix: str


@dataclass(frozen=True)
class GroupFrame:
    """Active block/function group with its starting statement index."""
    kind: Granularity
    start_stmt: int  # Index into stmt_checkpoints at group open.


@dataclass
class RollbackManager:
    """Tracks checkpoints and rollback scopes for decoding."""
    stmt_checkpoints: list[Checkpoint] = field(default_factory=list)
    # TODO: consider implicit root function/block; decide when renderer should open root groups.
    group_stack: list[GroupFrame] = field(default_factory=list)  # Open group frames in nesting order.
    retry_counters: dict[str, int] = field(default_factory=dict)  # Per-key retry counts.
    max_stmt_retries: int = 3
    max_block_retries: int = 2

    def add_stmt_checkpoint(self, prefix: str) -> None:
        self.stmt_checkpoints.append(Checkpoint(prefix=prefix))

    def open_group(self, kind: Granularity) -> None:
        if kind not in {Granularity.BLOCK, Granularity.FUNC}:
            return
        self.group_stack.append(GroupFrame(kind=kind, start_stmt=len(self.stmt_checkpoints)))

    def close_group(self, kind: Granularity) -> None:
        if kind not in {Granularity.BLOCK, Granularity.FUNC}:
            return
        for idx in range(len(self.group_stack) - 1, -1, -1):
            if self.group_stack[idx].kind == kind:
                del self.group_stack[idx:]
                return

    def apply_group_events(self, events: Sequence[GroupEvent]) -> None:
        for event in events:
            if event.action == GroupEventAction.OPEN:
                self.open_group(event.kind)
            elif event.action == GroupEventAction.CLOSE:
                self.close_group(event.kind)

    def sync_groups(self, desired: Sequence[Granularity]) -> None:
        """Synchronize group_stack to match the desired enclosing group kinds.

        This is intended to be called at COMMIT time, before adding the stmt checkpoint,
        so that open_group() records the correct start_stmt index.
        """
        desired_kinds = [kind for kind in desired if kind in {Granularity.BLOCK, Granularity.FUNC}]
        current_kinds = [frame.kind for frame in self.group_stack]

        k = 0
        while k < len(desired_kinds) and k < len(current_kinds) and desired_kinds[k] == current_kinds[k]:
            k += 1

        for kind in reversed(current_kinds[k:]):
            self.close_group(kind)
        for kind in desired_kinds[k:]:
            self.open_group(kind)

    def _truncate_to(self, keep_count: int) -> str:
        keep_count = max(0, keep_count)
        if keep_count < len(self.stmt_checkpoints):
            del self.stmt_checkpoints[keep_count:]
        self.group_stack = [g for g in self.group_stack if g.start_stmt < keep_count]
        if keep_count == 0:
            return ""
        return self.stmt_checkpoints[keep_count - 1].prefix

    def _last_checkpoint_prefix(self) -> str:
        if not self.stmt_checkpoints:
            return ""
        return self.stmt_checkpoints[-1].prefix

    def _target_start_for_scope(self, scope: RollbackScope) -> int | None:
        if scope == RollbackScope.BLOCK:
            for frame in reversed(self.group_stack):
                if frame.kind == Granularity.BLOCK:
                    return frame.start_stmt
            return None
        if scope == RollbackScope.FUNC:
            for frame in reversed(self.group_stack):
                if frame.kind == Granularity.FUNC:
                    return frame.start_stmt
            return None
        return None

    def rollback(self, scope: RollbackScope) -> str:
        if scope == RollbackScope.PROGRAM:
            self.stmt_checkpoints.clear()
            self.group_stack.clear()
            return ""
        if scope == RollbackScope.STMT:
            return self._last_checkpoint_prefix()
        target_start = self._target_start_for_scope(scope)
        if target_start is None:
            return self._last_checkpoint_prefix()
        return self._truncate_to(target_start)

    def record_retry(self, key: str) -> int:
        self.retry_counters[key] = self.retry_counters.get(key, 0) + 1
        return self.retry_counters[key]

