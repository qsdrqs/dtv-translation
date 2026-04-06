from __future__ import annotations

from dataclasses import dataclass

from core.types import OracleOutput, Granularity
from feedback.feedback import FeedbackState


@dataclass(frozen=True)
class RepairContext:
    failed_snippet: str
    repair_scope: Granularity
    outputs: tuple[OracleOutput, ...]
    parser_error_context: str | None = None

    @classmethod
    def from_feedback_state(
        cls,
        feedback_state: FeedbackState,
        bad_snippet: str,
        *,
        repair_scope: Granularity = Granularity.STMT,
        scope_filter: Granularity | None = None,
        parser_error_context: str | None = None,
    ) -> RepairContext:
        snippet = _normalize_failed_snippet(bad_snippet)
        parser_context = parser_error_context.strip() if parser_error_context else None
        outputs = feedback_state.active_snapshot()
        if scope_filter is not None:
            outputs = feedback_state.active_snapshot_for_scope(scope_filter)
        return cls(
            failed_snippet=snippet,
            repair_scope=repair_scope,
            outputs=outputs,
            parser_error_context=parser_context,
        )


def _normalize_failed_snippet(bad_snippet: str) -> str:
    if not bad_snippet.strip():
        return "(empty)"
    return bad_snippet.strip("\n")
