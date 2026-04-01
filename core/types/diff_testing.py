from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .enums import Granularity


@dataclass(frozen=True)
class TestCase:
    __test__ = False
    stdin: str = ""
    test_id: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_ms: float
    compilation_failed: bool = False


class TraceEventKind(Enum):
    FUNC_ENTER = "func_enter"
    FUNC_EXIT = "func_exit"
    BLOCK_ENTER = "block_enter"
    BLOCK_EXIT = "block_exit"


@dataclass(frozen=True)
class ExecutionTraceEvent:
    """A single trace event recorded during program execution (for diff testing)."""
    kind: TraceEventKind
    id: str
    timestamp_us: int | None = None
    depth: int | None = None
    args: list[dict[str, Any]] | None = None
    ret: dict[str, Any] | None = None
    ptr_args: list[dict[str, Any]] | None = None


@dataclass
class TraceSequence:
    events: list[ExecutionTraceEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Mismatch:
    position: int
    c_value: Any
    rust_value: Any
    message: str
    suggested_scope: Granularity | None = None


@dataclass
class ComparisonResult:
    matches: bool
    mismatches: list[Mismatch] = field(default_factory=list)
    cost: int = 1


@dataclass
class TranslationSample:
    """Generic sample for translation tasks (C->Rust, JS->TS, etc.)."""

    source_code: str
    source_lang: str  # "c", "js", etc.
    test_cases: list[TestCase] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
