from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


@dataclass(frozen=True)
class EslintResult:
    messages: list[dict]
    error_count: int
    elapsed_ms: int


class EslintDriver:
    def __init__(self, eslint_path: str = "eslint", config_path: str | None = None) -> None:
        self.eslint_command = _resolve_eslint_command(eslint_path)
        _check_eslint_version(self.eslint_command)
        self.project_root = _find_project_root()
        self.config_path = Path(config_path) if config_path is not None else _find_config_path()

    def check(self, code: str, timeout_s: float = 10.0) -> EslintResult:
        cmd = [
            *self.eslint_command,
            "--config",
            str(self.config_path),
            "--format",
            "json",
            "--stdin",
            "--stdin-filename",
            "check.ts",
        ]
        start = time.monotonic()
        try:
            completed = subprocess.run(
                cmd,
                input=code,
                capture_output=True,
                text=True,
                check=False,
                cwd=self.project_root,
                timeout=timeout_s,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"eslint not found: {' '.join(self.eslint_command)}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"eslint timed out after {timeout_s} seconds") from exc
        except OSError as exc:
            raise RuntimeError(f"eslint invocation failed: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"failed to parse eslint JSON output: stdout={completed.stdout!r} stderr={completed.stderr!r}"
            ) from exc

        if not isinstance(payload, list) or not payload:
            raise RuntimeError(f"unexpected eslint JSON payload: {payload!r}")
        report = payload[0]
        messages = report.get("messages")
        error_count = report.get("errorCount")
        if not isinstance(messages, list) or not isinstance(error_count, int):
            raise RuntimeError(f"unexpected eslint report shape: {report!r}")

        return EslintResult(
            messages=messages,
            error_count=error_count,
            elapsed_ms=elapsed_ms,
        )


def _resolve_eslint_command(eslint_path: str) -> list[str]:
    candidate = Path(eslint_path)
    if candidate.is_absolute() or candidate.parent != Path("."):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate)]
        raise RuntimeError(f"eslint not found or not executable: {eslint_path}")

    resolved = shutil.which(eslint_path)
    if resolved is not None:
        return [resolved]

    npx = shutil.which("npx")
    if npx is not None:
        return [npx, eslint_path]

    raise RuntimeError(f"eslint not found on PATH and npx unavailable: {eslint_path}")


def _check_eslint_version(eslint_command: list[str]) -> None:
    try:
        subprocess.run(
            [*eslint_command, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"failed to execute eslint --version: {exc}") from exc


def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "package.json").is_file():
            return current
        current = current.parent
    raise RuntimeError("could not locate project root for eslint")


def _find_config_path() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        candidate = current / "eslint.dtv.config.mjs"
        if candidate.is_file():
            return candidate
        current = current.parent
    raise RuntimeError("could not locate eslint.dtv.config.mjs")
