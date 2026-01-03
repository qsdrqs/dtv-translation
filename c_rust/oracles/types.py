from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.types import RollbackScope


@dataclass(frozen=True)
class TestCase:
    stdin: str = ""
    test_id: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    """
    Result of compiling and running a program.
    """
    exit_code: int | None  # None if timed out before exit.
    stdout: str
    stderr: str
    timed_out: bool  # True if timeout hit while compiling/running.
    elapsed_ms: float  # Wall-clock duration in milliseconds.
    compilation_failed: bool = False  # True if compile failed vs runtime.


class TraceEventKind(Enum):
    """Kind of trace event."""
    FUNC_ENTER = "func_enter"
    FUNC_EXIT = "func_exit"
    BLOCK_ENTER = "block_enter"
    BLOCK_EXIT = "block_exit"


@dataclass(frozen=True)
class TraceEvent:
    """
    A single trace event recorded during execution.
    """
    kind: TraceEventKind
    id: str
    timestamp_us: int | None = None  # Optional microsecond timestamp.
    depth: int | None = None  # Optional nesting depth.
    args: list[dict[str, Any]] | None = None  # JSON array of argument values.
    ret: dict[str, Any] | None = None  # JSON object for return value.
    ptr_args: list[dict[str, Any]] | None = None  # JSON array for pointer args on exit.


@dataclass
class TraceSequence:
    """
    Sequence of trace events from a single execution.
    """
    events: list[TraceEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # Extra context (test_id, language).


@dataclass(frozen=True)
class Mismatch:
    position: int
    c_value: Any
    rust_value: Any
    message: str
    suggested_scope: RollbackScope | None = None


@dataclass
class ComparisonResult:
    """
    Result of comparing C and Rust execution.
    """
    matches: bool
    mismatches: list[Mismatch] = field(default_factory=list)
    cost: int = 1  # Comparison cost units (for budgeting).


@dataclass
class DiffTestSample:
    """
    Complete sample data for differential testing.
    """
    c_source: str
    test_cases: list[TestCase] = field(default_factory=list)
    function_name: str | None = None  # Target function for function-level tests.
    block_mapping: dict[str, Any] = field(default_factory=dict)  # Block IDs to source locations.
