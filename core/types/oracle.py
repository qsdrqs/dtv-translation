from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact import Artifact, GroupStackFrame
from .enums import RollbackScope, Verdict


@dataclass(frozen=True)
class Diagnostic:
    message: str
    severity: str = "error"
    span: tuple[int, int] | None = None
    error_code: str | None = None
    hint_scope: RollbackScope | None = None


@dataclass(frozen=True)
class OracleOutput:
    oracle_name: str
    verdict: Verdict
    diagnostics: tuple[Diagnostic, ...] = ()
    realized_cost: int = 0


@dataclass(frozen=True)
class OracleContext:
    closed_stack: tuple[GroupStackFrame, ...] = ()
    closed_function_name: str | None = None
    sample: Any | None = None
    artifact: Artifact | None = None
    workdir: Path | None = None
    timeout_s: float | None = None
