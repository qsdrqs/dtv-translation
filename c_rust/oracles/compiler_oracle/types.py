from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.types import Artifact


@dataclass(frozen=True)
class OracleContext:
    """Inputs and environment for a single oracle run."""
    sample: Any | None  # Task-specific sample metadata (if available).
    artifact: Artifact
    workdir: Path  # Scratch directory for compiler artifacts.
    timeout_s: float | None = None  # Optional timeout for tooling.
