from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class Granularity(str, Enum):
    STMT = "stmt"
    BLOCK = "block"
    FUNC = "func"
    PROGRAM = "program"


@dataclass(frozen=True)
class Artifact:
    code: str
    granularity: Granularity
    metadata: dict[str, Any] = field(default_factory=dict)
    group_events: tuple[GroupEvent, ...] = ()


class RenderStatus(str, Enum):
    OK = "ok"
    CONTINUE = "continue"
    FAIL = "fail"


@dataclass(frozen=True)
class RenderResult:
    status: RenderStatus
    artifact: Artifact | None = None
    notes: str = ""


@dataclass(frozen=True)
class StopReason:
    kind: str
    detail: str = ""


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class GroupEventAction(str, Enum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class GroupEvent:
    action: GroupEventAction
    kind: Granularity


@dataclass(frozen=True)
class GenerateMessage:
    role: str
    content: str
    stop: bool = False


@dataclass
class GenerateContext:
    messages: Sequence[GenerateMessage | dict[str, Any]]
    steps: int = 0
    max_new_length: int = 1024


@dataclass(frozen=True)
class GenerateResult:
    delta_text: str
    delta_tokens: int
    stop_reason: StopReason


@dataclass(frozen=True)
class Diagnostic:
    message: str
    severity: str = "error"
    # TODO: decide canonical span representation (byte offsets vs line/col).
    span: tuple[int, int] | None = None
    error_code: str | None = None
    hint_scope: RollbackScope | None = None


@dataclass(frozen=True)
class OracleOutput:
    oracle_name: str
    verdict: Verdict
    diagnostics: tuple[Diagnostic, ...] = ()
    realized_cost: int = 0


class Action(str, Enum):
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
    prefix: str
    step: int = 0


@dataclass
class TraceEvent:
    step: int
    stop_reason: StopReason
    action: Action
    granularity: Granularity | None = None
    budget_snapshot: dict[str, Any] = field(default_factory=dict)
    oracle_outputs: tuple[OracleOutput, ...] = ()
    notes: str = ""
