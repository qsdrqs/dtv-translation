from __future__ import annotations

from dataclasses import dataclass, field

from core.types import OracleOutput, RollbackScope, Verdict


_ERROR_LEVELS = {"error", "fatal"}


@dataclass
class FeedbackState:
    """Stores recent oracle diagnostics for prompt augmentation."""
    max_items: int = 8  # Cap on stored messages.
    items: list[str] = field(default_factory=list)
    recent_outputs: list[OracleOutput] = field(default_factory=list)

    def update(
        self,
        outputs: list[OracleOutput],
        selected_scope: RollbackScope | None = None,
    ) -> None:
        current_items: list[str] = []
        self.recent_outputs = []
        fail_outputs = [output for output in outputs if output.verdict == Verdict.FAIL]
        if selected_scope is not None:
            fail_outputs = [
                output
                for output in fail_outputs
                if output.rollback_scope == selected_scope
            ]
            if not fail_outputs:
                raise ValueError("No FAIL outputs match selected rollback scope")

        for output in fail_outputs:
            filtered = tuple(
                diag for diag in output.diagnostics if _is_error_level(diag.severity)
            )
            if selected_scope is not None and not filtered:
                raise ValueError("FAIL output has no error/fatal diagnostics")
            if not filtered:
                continue
            self.recent_outputs.append(
                OracleOutput(
                    oracle_name=output.oracle_name,
                    verdict=output.verdict,
                    diagnostics=filtered,
                    realized_cost=output.realized_cost,
                    rollback_scope=output.rollback_scope,
                )
            )
            for diag in filtered:
                msg = f"[{output.oracle_name}] {diag.message}"
                current_items.append(msg)

        if len(current_items) > self.max_items:
            current_items = current_items[-self.max_items :]
        self.items = current_items

    def encode(self) -> str:
        if not self.items:
            return ""
        return "\n".join(self.items)

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
