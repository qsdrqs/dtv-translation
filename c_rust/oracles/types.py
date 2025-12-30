from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.types import Artifact


@dataclass(frozen=True)
class OracleContext:
    sample: Any | None
    artifact: Artifact
    workdir: Path
    timeout_s: float | None = None
