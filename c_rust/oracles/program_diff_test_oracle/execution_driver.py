"""Compilation and execution helpers for C and Rust oracles."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Sequence

from c_rust.oracles.program_diff_test_oracle.difftesting_types import ExecutionResult, TestCase


class CompilationDriver:
    """Base class for language-specific compilation drivers."""

    def __init__(self, compiler_path: str, timeout_s: float | None = 10.0) -> None:
        self.compiler_path = compiler_path
        self.timeout_s = timeout_s
        self._validate_compiler()

    def _validate_compiler(self) -> None:
        try:
            result = subprocess.run(
                [self.compiler_path, "--version"],
                capture_output=True,
                timeout=5.0,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Compiler {self.compiler_path} failed version check")
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"Compiler {self.compiler_path} not found or not working") from e

    def compile(self, source_code: str, workdir: Path) -> ExecutionResult:
        raise NotImplementedError


class GccDriver(CompilationDriver):
    """Driver for compiling C programs with gcc."""

    def __init__(
        self,
        compiler_path: str = "gcc",
        timeout_s: float | None = 10.0,
        extra_flags: Sequence[str] = (),
    ) -> None:
        super().__init__(compiler_path, timeout_s)
        self.extra_flags = list(extra_flags)

    def compile(self, source_code: str, workdir: Path) -> ExecutionResult:
        """Compile C source code into a binary in workdir."""
        source_file = workdir / "program.c"
        binary_file = workdir / "program"

        source_file.write_text(source_code, encoding="utf-8")

        compile_cmd = [
            self.compiler_path,
            "-o", str(binary_file),
            str(source_file),
            "-std=c11",
            "-Wall",
        ] + self.extra_flags

        start_time = time.time()
        try:
            result = subprocess.run(
                compile_cmd,
                capture_output=True,
                timeout=self.timeout_s,
                cwd=workdir,
                check=False,
                text=True,
            )
            elapsed_ms = (time.time() - start_time) * 1000

            compilation_failed = result.returncode != 0

            return ExecutionResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=False,
                elapsed_ms=elapsed_ms,
                compilation_failed=compilation_failed,
            )

        except subprocess.TimeoutExpired as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return ExecutionResult(
                exit_code=None,
                stdout=e.stdout.decode("utf-8", errors="replace") if e.stdout else "",
                stderr=e.stderr.decode("utf-8", errors="replace") if e.stderr else "",
                timed_out=True,
                elapsed_ms=elapsed_ms,
                compilation_failed=True,
            )


class RustcCompilationDriver(CompilationDriver):
    """Driver for compiling Rust programs with rustc."""

    def __init__(
        self,
        compiler_path: str = "rustc",
        timeout_s: float | None = 10.0,
        extra_flags: Sequence[str] = (),
    ) -> None:
        super().__init__(compiler_path, timeout_s)
        self.extra_flags = list(extra_flags)

    def compile(self, source_code: str, workdir: Path) -> ExecutionResult:
        """Compile Rust source code into a binary in workdir."""
        source_file = workdir / "program.rs"
        binary_file = workdir / "program"

        source_file.write_text(source_code, encoding="utf-8")

        compile_cmd = [
            self.compiler_path,
            "-o", str(binary_file),
            str(source_file),
            "--edition=2021",
        ] + self.extra_flags

        start_time = time.time()
        try:
            result = subprocess.run(
                compile_cmd,
                capture_output=True,
                timeout=self.timeout_s,
                cwd=workdir,
                check=False,
                text=True,
            )
            elapsed_ms = (time.time() - start_time) * 1000

            compilation_failed = result.returncode != 0

            return ExecutionResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=False,
                elapsed_ms=elapsed_ms,
                compilation_failed=compilation_failed,
            )

        except subprocess.TimeoutExpired as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return ExecutionResult(
                exit_code=None,
                stdout=e.stdout.decode("utf-8", errors="replace") if e.stdout else "",
                stderr=e.stderr.decode("utf-8", errors="replace") if e.stderr else "",
                timed_out=True,
                elapsed_ms=elapsed_ms,
                compilation_failed=True,
            )


def run_binary(
    binary_path: Path,
    test_case: TestCase,
    timeout_s: float | None = 5.0,
) -> ExecutionResult:
    """Run a compiled binary with a single test input."""
    start_time = time.time()
    try:
        result = subprocess.run(
            [str(binary_path)],
            input=test_case.stdin,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            text=True,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
            elapsed_ms=elapsed_ms,
            compilation_failed=False,
        )

    except subprocess.TimeoutExpired as e:
        elapsed_ms = (time.time() - start_time) * 1000
        return ExecutionResult(
            exit_code=None,
            stdout=e.stdout.decode("utf-8", errors="replace") if e.stdout else "",
            stderr=e.stderr.decode("utf-8", errors="replace") if e.stderr else "",
            timed_out=True,
            elapsed_ms=elapsed_ms,
            compilation_failed=False,
        )


def compile_and_run(
    source_code: str,
    test_cases: Sequence[TestCase],
    language: str,
    workdir: Path,
    compile_timeout_s: float | None = 10.0,
    run_timeout_s: float | None = 5.0,
    compiler_path: str | None = None,
) -> tuple[ExecutionResult, list[ExecutionResult]]:
    """Compile source code and run it against multiple test cases."""
    if language == "c":
        driver = GccDriver(
            compiler_path=compiler_path or "gcc",
            timeout_s=compile_timeout_s,
        )
    elif language == "rust":
        driver = RustcCompilationDriver(
            compiler_path=compiler_path or "rustc",
            timeout_s=compile_timeout_s,
        )
    else:
        raise ValueError(f"Unsupported language: {language}")

    compile_result = driver.compile(source_code, workdir)

    if compile_result.compilation_failed or compile_result.timed_out:
        # return early if compilation failed or timed out
        return compile_result, []

    binary_path = workdir / "program"
    execution_results = []

    for test_case in test_cases:
        exec_result = run_binary(binary_path, test_case, timeout_s=run_timeout_s)
        execution_results.append(exec_result)

    return compile_result, execution_results
