from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact import Artifact, GroupStackFrame
from .enums import Granularity, RollbackScope, Verdict


@dataclass(frozen=True)
class DiagnosticSpan:
    line: int
    col: int = 0
    message: str = ""
    is_primary: bool = False


@dataclass(frozen=True)
class Diagnostic:
    message: str
    severity: str = "error"
    spans: tuple[DiagnosticSpan, ...] = ()
    error_code: str | None = None
    hint_scope: RollbackScope | None = None
    hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class OracleOutput:
    oracle_name: str
    verdict: Verdict
    diagnostics: tuple[Diagnostic, ...] = ()
    realized_cost: int = 0
    rollback_scope: RollbackScope | None = None


@dataclass(frozen=True)
class OracleContext:
    closed_stack: tuple[GroupStackFrame, ...] = ()
    closed_function_name: str | None = None
    sample: Any | None = None
    artifact: Artifact | None = None
    workdir: Path | None = None
    timeout_s: float | None = None
