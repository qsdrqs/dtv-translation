from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from tree_sitter import Tree


class Granularity(str, Enum):
    STMT = "stmt"
    BLOCK = "block"
    FUNC = "func"
    PROGRAM = "program"


@dataclass(frozen=True)
class Artifact:
    """Renderable code artifact and its decoding metadata."""
    code: str
    granularity: Granularity
    ast_tree: Tree | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO: remove - migrate all fields to explicit typed attributes.
    group_events: tuple[GroupEvent, ...] = ()  # OPEN/CLOSE events for rollback grouping.
    group_stack: tuple[Granularity, ...] | None = None  # Enclosing groups at prefix end (outer -> inner).


class RenderStatus(str, Enum):
    OK = "ok"
    CONTINUE = "continue"
    FAIL = "fail"


@dataclass(frozen=True)
class RenderResult:
    """Outcome of attempting to render a prefix at a given granularity."""
    status: RenderStatus
    artifact: Artifact | None = None
    notes: str = ""  # Debug notes for logging or UI.


@dataclass(frozen=True)
class StopReason:
    """Best-effort label for why decoding stopped."""
    kind: str
    detail: str = ""  # Optional extra detail (e.g., token limit).


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class GroupEventAction(str, Enum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class GroupEvent:
    """Group boundary event emitted by renderers."""
    action: GroupEventAction
    kind: Granularity


@dataclass(frozen=True)
class GenerateMessage:
    """Chat-style message used to build model prompts."""
    role: str
    content: str
    stop: bool = False  # Insert a hard boundary when constructing raw prompts.


@dataclass
class GenerateContext:
    """Inputs for one generation step."""
    messages: Sequence[GenerateMessage | dict[str, Any]]
    steps: int = 0  # Controller step index (for logging or policy).
    max_new_length: int = 1024  # Per-step token budget.


@dataclass(frozen=True)
class GenerateResult:
    """Delta produced by a single generation step."""
    delta_text: str
    delta_tokens: int
    stop_reason: StopReason


@dataclass(frozen=True)
class Diagnostic:
    """Diagnostic emitted by an oracle or parser."""
    message: str
    severity: str = "error"
    # TODO: decide canonical span representation (byte offsets vs line/col).
    span: tuple[int, int] | None = None  # Byte offsets in rendered source.
    error_code: str | None = None  # Tool-specific error identifier.
    hint_scope: RollbackScope | None = None  # Suggested rollback scope, if any.


@dataclass(frozen=True)
class OracleOutput:
    """Result from a deterministic oracle run."""
    oracle_name: str
    verdict: Verdict
    diagnostics: tuple[Diagnostic, ...] = ()
    realized_cost: int = 0  # Cost units charged to the budget.


class Action(str, Enum):
    GENERATE = "generate"
    VERIFY = "verify"
    FEEDBACK = "feedback"
    APPLY_PATCH = "apply_patch"
    CONTINUE = "continue"
    COMMIT = "commit"
    ROLLBACK = "rollback"
    TERMINATE = "terminate"


class RollbackScope(str, Enum):
    STMT = "stmt"
    BLOCK = "block"
    FUNC = "func"
    PROGRAM = "program"


@dataclass
class ControllerState:
    """Mutable controller state for the decoding loop."""
    prefix: str
    step: int = 0  # Step counter.


@dataclass
class TraceEvent:
    """Per-step trace for debugging and analysis."""
    step: int
    stop_reason: StopReason | None
    action: Action
    granularity: Granularity | None = None
    render_status: RenderStatus | None = None
    rollback_scope: RollbackScope | None = None
    patch_applied: bool = False
    budget_snapshot: dict[str, Any] = field(default_factory=dict)  # Copy of Budget.snapshot().
    oracle_outputs: tuple[OracleOutput, ...] = ()  # Outputs from oracles run at this step.
    notes: str = ""  # Debug notes for analysis.

