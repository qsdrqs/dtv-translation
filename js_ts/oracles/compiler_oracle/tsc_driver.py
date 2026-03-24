from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import time

from core.types import OracleContext

_TSC_CHECK_SCRIPT = Path(__file__).resolve().parent / "tsc_check.js"


@dataclass(frozen=True)
class TscResult:
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int
    command: tuple[str, ...]
    source_path: Path
    timed_out: bool = False


class TscDriver:
    def __init__(
        self,
        node_path: str = "node",
        type_roots: tuple[str, ...] | None = None,
    ) -> None:
        self.node_path = _resolve_node_path(node_path)
        if type_roots is not None:
            self.type_roots = type_roots
        else:
            discovered = _find_type_roots()
            self.type_roots = (discovered,) if discovered else ()

    def check(self, ctx: OracleContext) -> TscResult:
        if ctx.workdir is None or ctx.artifact is None:
            raise ValueError("OracleContext missing workdir or artifact")
        workdir = ctx.workdir
        artifact = ctx.artifact
        source_path = workdir / "check.ts"
        source_path.write_text(artifact.code, encoding="utf-8")

        type_roots_args: tuple[str, ...] = ()
        if self.type_roots:
            type_roots_args = ("--typeRoots", ",".join(self.type_roots))

        cmd = (
            self.node_path,
            str(_TSC_CHECK_SCRIPT),
            str(source_path),
            *type_roots_args,
        )

        start = time.monotonic()
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=ctx.timeout_s,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"node not found: {self.node_path}") from exc
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            stdout_str: str = exc.stdout.decode("utf-8") if isinstance(exc.stdout, bytes) else (str(exc.stdout) if exc.stdout else "")
            stderr_str: str = exc.stderr.decode("utf-8") if isinstance(exc.stderr, bytes) else (str(exc.stderr) if exc.stdout else "")
            return TscResult(
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=124,
                elapsed_ms=elapsed_ms,
                command=cmd,
                source_path=source_path,
                timed_out=True,
            )
        except OSError as exc:
            raise RuntimeError(f"tsc_check invocation failed: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return TscResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            elapsed_ms=elapsed_ms,
            command=cmd,
            source_path=source_path,
            timed_out=False,
        )


def _resolve_node_path(node_path: str) -> str:
    resolved = shutil.which(node_path)
    if not resolved:
        raise RuntimeError(f"node not found on PATH: {node_path}")
    return resolved


def _find_type_roots() -> str | None:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        candidate = current / "node_modules" / "@types"
        if candidate.is_dir():
            return str(candidate)
        current = current.parent
    return None
