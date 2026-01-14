from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import Action, Granularity, RenderStatus, RollbackScope
from .generation import StopReason
from .oracle import OracleOutput


@dataclass
class ControllerState:
    prefix: str
    step: int = 0


@dataclass
class TraceEvent:
    step: int
    stop_reason: StopReason | None
    action: Action
    granularity: Granularity | None = None
    render_status: RenderStatus | None = None
    rollback_scope: RollbackScope | None = None
    patch_applied: bool = False
    budget_snapshot: dict[str, Any] = field(default_factory=dict)
    oracle_outputs: tuple[OracleOutput, ...] = ()
    notes: str = ""
