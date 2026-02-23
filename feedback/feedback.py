from __future__ import annotations

from dataclasses import dataclass, field

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
        self._refresh_views()

    def on_rollback(self, selected_scope: RollbackScope) -> None:
        _ = selected_scope

    def on_commit(self, committed_scope: RollbackScope | None) -> None:
        _ = committed_scope

    def on_terminate(self) -> None:
        self._active_outputs = {}
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

    def encode(self) -> str:
        if not self.items:
            return ""
        return "\n".join(self.items)

    def active_snapshot(self) -> tuple[OracleOutput, ...]:
        return tuple(self._sorted_active_outputs())

    def augment_prompt(self, base_prompt: str) -> str:
        feedback = self.encode()
        if not feedback:
            return base_prompt
        return f"{base_prompt}\n\n# Feedback\n{feedback}\n"

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
