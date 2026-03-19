from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import time

from core.types import OracleContext


@dataclass(frozen=True)
class TscResult:
    """Captured result of invoking tsc."""
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int  # Wall-clock compile time in milliseconds.
    command: tuple[str, ...]  # Exact command line invoked.
    source_path: Path  # TypeScript source file written to disk.
    timed_out: bool = False  # True if the compiler timed out.


class TscDriver:
    def __init__(
        self,
        tsc_path: str = "tsc",
        type_roots: tuple[str, ...] | None = None,
    ) -> None:
        self.tsc_path = _resolve_tsc_path(tsc_path)
        _check_tsc_version(self.tsc_path)
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
            self.tsc_path,
            "--noEmit",
            "--pretty", "false",
            "--strict",
            "--target", "ES2020",
            "--lib", "ES2020,DOM",
            "--skipLibCheck",
            *type_roots_args,
            str(source_path),
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
            raise RuntimeError(f"tsc not found: {self.tsc_path}") from exc
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            stdout_str: str = exc.stdout.decode("utf-8") if isinstance(exc.stdout, bytes) else (str(exc.stdout) if exc.stdout else "")
            stderr_str: str = exc.stderr.decode("utf-8") if isinstance(exc.stderr, bytes) else (str(exc.stderr) if exc.stderr else "")
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
            raise RuntimeError(f"tsc invocation failed: {exc}") from exc

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


def _resolve_tsc_path(tsc_path: str) -> str:
    candidate = Path(tsc_path)
    if candidate.is_absolute() or candidate.parent != Path("."):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise RuntimeError(f"tsc not found or not executable: {tsc_path}")
    resolved = shutil.which(tsc_path)
    if not resolved:
        raise RuntimeError(f"tsc not found on PATH: {tsc_path}")
    return resolved


def _check_tsc_version(tsc_path: str) -> None:
    try:
        subprocess.run(
            (tsc_path, "--version"),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"failed to execute tsc --version: {exc}") from exc


def _find_type_roots() -> str | None:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        candidate = current / "node_modules" / "@types"
        if candidate.is_dir():
            return str(candidate)
        current = current.parent
    return None
