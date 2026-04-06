from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from core.llm_output import AssistantContent, DEFAULT_WRITE_REGION_MARKERS, OutputExtractorState, WriteRegionMarkers
from core.types import Granularity, GroupEvent, GroupEventAction, GroupStackFrame


@dataclass
class Checkpoint:
    """Snapshot of the prefix after a committed statement."""
    code_prefix: str
    assistant_prefix: AssistantContent
    extractor_state: OutputExtractorState | None = None


@dataclass
class RollbackManager:
    """Tracks checkpoints and rollback scopes for decoding."""
    stmt_checkpoints: list[Checkpoint] = field(default_factory=list)
    # TODO: consider implicit root function/block; decide when renderer should open root groups.
    group_stack: list[GroupStackFrame] = field(default_factory=list)  # Open group frames in nesting order.
    retry_counters: dict[str, int] = field(default_factory=dict)  # Per-key retry counts.
    max_stmt_retries: int = 3
    max_block_retries: int = 2
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS
    write_anchor: Checkpoint | None = None

    def add_stmt_checkpoint(
        self,
        code_prefix: str,
        assistant_prefix: AssistantContent,
        extractor_state: OutputExtractorState | None,
    ) -> None:
        self.stmt_checkpoints.append(
            Checkpoint(
                code_prefix=code_prefix,
                assistant_prefix=assistant_prefix,
                extractor_state=extractor_state,
            )
        )

    def set_write_anchor(
        self,
        assistant_prefix: AssistantContent,
        extractor_state: OutputExtractorState | None,
    ) -> None:
        if self.write_anchor is not None:
            return
        self.write_anchor = Checkpoint(
            code_prefix="",
            assistant_prefix=assistant_prefix,
            extractor_state=extractor_state,
        )

    def open_group(
        self,
        kind: Granularity,
        *,
        name_id: str | None = None,
        group_id: str | None = None,
    ) -> None:
        if kind not in {Granularity.BLOCK, Granularity.FUNC}:
            return
        self.group_stack.append(
            GroupStackFrame(
                kind=kind,
                name_id=name_id,
                group_id=group_id,
                start_stmt=len(self.stmt_checkpoints),
            )
        )

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

    def sync_groups(self, desired: Sequence[GroupStackFrame]) -> None:
        """Synchronize group_stack to match the desired enclosing group kinds.

        This is intended to be called at COMMIT time, before adding the stmt checkpoint,
        so that open_group() records the correct start_stmt index.
        """
        desired_frames = [
            frame
            for frame in desired
            if frame.kind in {Granularity.BLOCK, Granularity.FUNC}
        ]

        k = 0
        while (
            k < len(desired_frames)
            and k < len(self.group_stack)
            and GroupStackFrame.matches(desired_frames[k], self.group_stack[k])
        ):
            k += 1

        for frame in reversed(self.group_stack[k:]):
            self.close_group(frame.kind)
        for frame in desired_frames[k:]:
            self.open_group(
                frame.kind,
                name_id=frame.name_id,
                group_id=frame.group_id,
            )

    def _truncate_to(self, keep_count: int) -> Checkpoint:
        keep_count = max(0, keep_count)
        if keep_count < len(self.stmt_checkpoints):
            del self.stmt_checkpoints[keep_count:]
        self.group_stack = [
            g
            for g in self.group_stack
            if g.start_stmt is not None and g.start_stmt < keep_count
        ]
        if keep_count == 0:
            return Checkpoint(
                code_prefix="",
                assistant_prefix=AssistantContent.empty(markers=self.markers),
                extractor_state=None,
            )
        return self.stmt_checkpoints[keep_count - 1]

    def _last_checkpoint(self) -> Checkpoint:
        if not self.stmt_checkpoints:
            return Checkpoint(
                code_prefix="",
                assistant_prefix=AssistantContent.empty(markers=self.markers),
                extractor_state=None,
            )
        return self.stmt_checkpoints[-1]

    def _apply_write_anchor_floor(self, checkpoint: Checkpoint) -> Checkpoint:
        if self.write_anchor is None:
            return checkpoint
        if len(checkpoint.code_prefix) > len(self.write_anchor.code_prefix):
            return checkpoint
        return self.write_anchor

    def _target_start_for_scope(self, scope: Granularity) -> int | None:
        if scope == Granularity.BLOCK:
            for frame in reversed(self.group_stack):
                if frame.kind == Granularity.BLOCK:
                    return frame.start_stmt
            return None
        if scope == Granularity.FUNC:
            for frame in reversed(self.group_stack):
                if frame.kind == Granularity.FUNC:
                    return frame.start_stmt
            return None
        return None

    def rollback(self, scope: Granularity) -> Checkpoint:
        if scope == Granularity.PROGRAM:
            self.stmt_checkpoints.clear()
            self.group_stack.clear()
            return self._apply_write_anchor_floor(
                Checkpoint(
                    code_prefix="",
                    assistant_prefix=AssistantContent.empty(markers=self.markers),
                    extractor_state=None,
                )
            )
        if scope == Granularity.STMT:
            return self._apply_write_anchor_floor(self._last_checkpoint())
        target_start = self._target_start_for_scope(scope)
        if target_start is None:
            return self._apply_write_anchor_floor(self._last_checkpoint())
        return self._apply_write_anchor_floor(self._truncate_to(target_start))

    def record_retry(self, key: str) -> int:
        self.retry_counters[key] = self.retry_counters.get(key, 0) + 1
        return self.retry_counters[key]
