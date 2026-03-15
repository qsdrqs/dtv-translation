from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@dataclass(frozen=True)
class TscCheckResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class NodeRunResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


def _tsc_path() -> str:
    tsc = shutil.which("tsc")
    if tsc is None:
        pytest.skip("tsc not available")
    try:
        subprocess.run([tsc, "--version"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("tsc not functional")
    return tsc


def _node_path() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    try:
        subprocess.run([node, "--version"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("node not functional")
    return node


def check_typescript(code: str) -> TscCheckResult:
    tsc = _tsc_path()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "check.ts"
        src.write_text(code, encoding="utf-8")
        proc = subprocess.run(
            [tsc, "--noEmit", "--pretty", "false", "--strict",
             "--target", "ES2020", "--lib", "ES2020,DOM", str(src)],
            capture_output=True,
            text=True,
            check=False,
        )
    return TscCheckResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )


def run_node(code: str, *, stdin: str = "", timeout_s: float = 10) -> NodeRunResult:
    node = _node_path()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "run.js"
        src.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [node, str(src)],
                input=stdin,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
            return NodeRunResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            return NodeRunResult(
                stdout=exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "",
                stderr=exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "",
                exit_code=None,
                timed_out=True,
            )
