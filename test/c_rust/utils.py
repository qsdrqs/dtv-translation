from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@dataclass(frozen=True)
class RustcResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


def _rustc_path() -> str:
    rustc = shutil.which("rustc")
    if rustc is None:
        pytest.skip("rustc not available; skipping rust renderer tests")
    return rustc


def compile_rust(code: str, crate_type: str = "lib") -> RustcResult:
    rustc = _rustc_path()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "lib.rs"
        out = tmp / "lib.rlib"
        src.write_text(code, encoding="utf-8")
        proc = subprocess.run(
            [
                rustc,
                "--edition",
                "2021",
                "--crate-type",
                crate_type,
                str(src),
                "-o",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    return RustcResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )
