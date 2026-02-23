from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence

from core.types import OracleOutput, RollbackScope, Verdict


_ERROR_LEVELS = {"error", "fatal"}


def _scope_for_output(
    output: OracleOutput,
    fallback_scope: RollbackScope | None,
) -> RollbackScope:
    if output.rollback_scope is not None:
        return output.rollback_scope
    if fallback_scope is not None:
        return fallback_scope
    raise ValueError(
        "OracleOutput.rollback_scope must be set when selected_scope is not provided"
    )


def _copy_with_filtered_diagnostics(
    output: OracleOutput,
    scope: RollbackScope,
) -> OracleOutput | None:
    filtered = tuple(diag for diag in output.diagnostics if _is_error_level(diag.severity))
    if not filtered:
        return None
    return OracleOutput(
        oracle_name=output.oracle_name,
        verdict=output.verdict,
        diagnostics=filtered,
        realized_cost=output.realized_cost,
        rollback_scope=scope,
    )


@dataclass
class FeedbackState:
    """Stores recent oracle diagnostics for prompt augmentation."""
    max_items: int = 8  # Cap on stored messages.
    items: list[str] = field(default_factory=list)
    recent_outputs: list[OracleOutput] = field(default_factory=list)
    _active_outputs: dict[tuple[str, RollbackScope], OracleOutput] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _scope_anchor_offsets: dict[RollbackScope, int] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def on_verify(
        self,
        outputs: list[OracleOutput],
        selected_scope: RollbackScope | None = None,
    ) -> None:
        for output in outputs:
            scope = _scope_for_output(output, selected_scope)
            if selected_scope is not None and scope != selected_scope:
                continue
            key = (output.oracle_name, scope)
            if output.verdict == Verdict.FAIL:
                filtered_output = _copy_with_filtered_diagnostics(output, scope)
                if filtered_output is None:
                    raise ValueError("FAIL output has no error/fatal diagnostics")
                self._active_outputs[key] = filtered_output
                continue
            if output.verdict in {Verdict.PASS, Verdict.NOT_APPLICABLE}:
                self._active_outputs.pop(key, None)
        self._prune_scope_anchors()
        self._refresh_views()

    def on_rollback(self, selected_scope: RollbackScope) -> None:
        _ = selected_scope

    def bind_failures_to_scope(
        self,
        outputs: Sequence[OracleOutput],
        selected_scope: RollbackScope,
    ) -> None:
        updated = False
        for output in outputs:
            if output.verdict != Verdict.FAIL:
                continue
            source_scope = _scope_for_output(output, selected_scope)
            owner_scope = source_scope
            if selected_scope > source_scope:
                owner_scope = selected_scope
            filtered_output = _copy_with_filtered_diagnostics(output, owner_scope)
            if filtered_output is None:
                raise ValueError("FAIL output has no error/fatal diagnostics")
            self._drop_oracle_entries(output.oracle_name)
            self._active_outputs[(output.oracle_name, owner_scope)] = filtered_output
            updated = True
        if not updated:
            return
        self._prune_scope_anchors()
        self._refresh_views()

    def on_commit(self, committed_scope: RollbackScope | None) -> None:
        if committed_scope is None:
            return
        stale_keys = [
            key
            for key in self._active_outputs
            if key[1] <= committed_scope
        ]
        for key in stale_keys:
            del self._active_outputs[key]
        self._prune_scope_anchors()
        self._refresh_views()

    def on_terminate(self) -> None:
        self._active_outputs = {}
        self._scope_anchor_offsets = {}
        self._refresh_views()

    def _sorted_active_outputs(self) -> list[OracleOutput]:
        ordered = sorted(
            self._active_outputs.items(),
            key=lambda item: item[0][1],
            reverse=True,
        )
        return [output for _, output in ordered]

    def _refresh_views(self) -> None:
        ordered_outputs = self._sorted_active_outputs()
        current_items: list[str] = []
        for output in ordered_outputs:
            for diag in output.diagnostics:
                current_items.append(f"[{output.oracle_name}] {diag.message}")
        if len(current_items) > self.max_items:
            current_items = current_items[-self.max_items :]
        self.recent_outputs = ordered_outputs
        self.items = current_items

    def _prune_scope_anchors(self) -> None:
        _prune_anchor_offsets(self._active_outputs, self._scope_anchor_offsets)

    def encode(self) -> str:
        if not self.items:
            return ""
        return "\n".join(self.items)

    def active_snapshot(self) -> tuple[OracleOutput, ...]:
        return tuple(self._sorted_active_outputs())

    def active_snapshot_for_scope(self, scope: RollbackScope) -> tuple[OracleOutput, ...]:
        outputs = [
            output
            for output in self._sorted_active_outputs()
            if output.rollback_scope == scope
        ]
        return tuple(outputs)

    def scoped_active_snapshot(
        self,
    ) -> tuple[tuple[RollbackScope, int | None, tuple[OracleOutput, ...]], ...]:
        grouped: dict[RollbackScope, list[OracleOutput]] = {}
        for (_, scope), output in self._active_outputs.items():
            grouped.setdefault(scope, []).append(output)
        rows: list[tuple[RollbackScope, int | None, tuple[OracleOutput, ...]]] = []
        for scope, outputs in grouped.items():
            rows.append(
                (
                    scope,
                    self._scope_anchor_offsets.get(scope),
                    tuple(sorted(outputs, key=lambda output: output.oracle_name)),
                )
            )
        rows.sort(key=lambda item: item[0], reverse=True)
        return tuple(rows)

    def set_scope_anchor(self, scope: RollbackScope, code_offset: int) -> None:
        if code_offset < 0:
            raise ValueError("code_offset must be >= 0")
        self._scope_anchor_offsets[scope] = code_offset

    def _drop_oracle_entries(self, oracle_name: str) -> None:
        stale_keys = [key for key in self._active_outputs if key[0] == oracle_name]
        for key in stale_keys:
            del self._active_outputs[key]

    def best_fix_hint(self) -> str | None:
        for output in self.recent_outputs:
            for diag in output.diagnostics:
                for hint in diag.hints:
                    text = hint.strip()
                    if text:
                        return text
                fallback = _extract_help_from_message(diag.message)
                if fallback is not None:
                    return fallback
        return None


def _extract_help_from_message(message: str) -> str | None:
    for line in message.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("help:"):
            candidate = stripped.split(":", 1)[1].strip()
            if candidate:
                return candidate
    return None


def _is_error_level(severity: str) -> bool:
    level = severity.lower().strip()
    return level in _ERROR_LEVELS


def _active_scopes(
    active_outputs: dict[tuple[str, RollbackScope], OracleOutput],
) -> set[RollbackScope]:
    return {scope for _, scope in active_outputs}


def _prune_anchor_offsets(
    active_outputs: dict[tuple[str, RollbackScope], OracleOutput],
    anchor_offsets: dict[RollbackScope, int],
) -> None:
    scopes = _active_scopes(active_outputs)
    stale_scopes = [scope for scope in anchor_offsets if scope not in scopes]
    for scope in stale_scopes:
        del anchor_offsets[scope]
