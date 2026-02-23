from __future__ import annotations

from dataclasses import dataclass

from core.types import OracleOutput, RollbackScope
from feedback.feedback import FeedbackState


@dataclass(frozen=True)
class RepairContext:
    failed_snippet: str
    repair_scope: RollbackScope
    outputs: tuple[OracleOutput, ...]
    parser_error_context: str | None = None

    @classmethod
    def from_feedback_state(
        cls,
        feedback_state: FeedbackState,
        bad_snippet: str,
        *,
        repair_scope: RollbackScope = RollbackScope.STMT,
        parser_error_context: str | None = None,
    ) -> RepairContext:
        snippet = bad_snippet.strip() or "(empty)"
        parser_context = parser_error_context.strip() if parser_error_context else None
        return cls(
            failed_snippet=snippet,
            repair_scope=repair_scope,
            outputs=feedback_state.active_snapshot(),
            parser_error_context=parser_context,
        )
