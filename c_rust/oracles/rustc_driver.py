from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import time

from c_rust.oracles.types import OracleContext


@dataclass(frozen=True)
class RustcResult:
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int
    command: tuple[str, ...]
    source_path: Path
    output_path: Path
    timed_out: bool = False


class RustcDriver:
    def __init__(self, rustc_path: str = "rustc") -> None:
        self.rustc_path = _resolve_rustc_path(rustc_path)
        _check_rustc_version(self.rustc_path)

    def compile(self, ctx: OracleContext) -> RustcResult:
        source_path = ctx.workdir / "main.rs"
        output_path = ctx.workdir / "dtv_out"
        source_path.write_text(ctx.artifact.code, encoding="utf-8")

        cmd = (
            self.rustc_path,
            str(source_path),
            "--error-format=json",
            "--crate-type",
            "lib",
            "--edition",
            "2021",
            "-o",
            str(output_path),
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
            raise RuntimeError(f"rustc not found: {self.rustc_path}") from exc
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return RustcResult(
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                exit_code=124,
                elapsed_ms=elapsed_ms,
                command=cmd,
                source_path=source_path,
                output_path=output_path,
                timed_out=True,
            )
        except OSError as exc:
            raise RuntimeError(f"rustc invocation failed: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return RustcResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            elapsed_ms=elapsed_ms,
            command=cmd,
            source_path=source_path,
            output_path=output_path,
            timed_out=False,
        )


def _resolve_rustc_path(rustc_path: str) -> str:
    candidate = Path(rustc_path)
    if candidate.is_absolute() or candidate.parent != Path("."):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise RuntimeError(f"rustc not found or not executable: {rustc_path}")
    resolved = shutil.which(rustc_path)
    if not resolved:
        raise RuntimeError(f"rustc not found on PATH: {rustc_path}")
    return resolved


def _check_rustc_version(rustc_path: str) -> None:
    try:
        subprocess.run(
            (rustc_path, "--version"),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"failed to execute rustc --version: {exc}") from exc
