"""
Tests for program-level differential oracle.
"""

from pathlib import Path
import pytest

from core.types import Artifact, ControllerState, Granularity, OracleContext, TestCase, TranslationSample, Verdict
from c_rust.oracles.program_diff_test_oracle.program_oracle import ProgramOracle
from test.c_rust.utils import _gcc_path, _rustc_path


# Sample C and Rust programs for testing


C_HELLO_WORLD = """
#include <stdio.h>

int main() {
    printf("Hello, World!\\n");
    return 0;
}
"""

RUST_HELLO_WORLD = """
fn main() {
    println!("Hello, World!");
}
"""

C_ECHO_INPUT = """
#include <stdio.h>

int main() {
    int n;
    scanf("%d", &n);
    printf("You entered: %d\\n", n);
    return 0;
}
"""

RUST_ECHO_INPUT = """
use std::io;

fn main() {
    let mut input = String::new();
    io::stdin().read_line(&mut input).unwrap();
    let n: i32 = input.trim().parse().unwrap();
    println!("You entered: {}", n);
}
"""

C_EXIT_CODE = """
#include <stdlib.h>

int main() {
    return 42;
}
"""

RUST_EXIT_CODE_CORRECT = """
fn main() {
    std::process::exit(42);
}
"""

RUST_EXIT_CODE_WRONG = """
fn main() {
    std::process::exit(0);
}
"""

C_WRONG_OUTPUT = """
#include <stdio.h>

int main() {
    printf("Hello\\n");
    return 0;
}
"""

RUST_WRONG_OUTPUT = """
fn main() {
    println!("Goodbye");
}
"""


def test_program_oracle_pass_simple():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_HELLO_WORLD,
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="hello")],
    )

    artifact = Artifact(
        code=RUST_HELLO_WORLD,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.PASS
    assert result.oracle_name == "program_diff"
    assert len(result.diagnostics) == 0
    assert result.realized_cost > 0


def test_program_oracle_pass_with_input():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_ECHO_INPUT,
        source_lang="c",
        test_cases=[
            TestCase(stdin="42\n", test_id="echo_42"),
            TestCase(stdin="100\n", test_id="echo_100"),
        ],
    )

    artifact = Artifact(
        code=RUST_ECHO_INPUT,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.PASS
    assert len(result.diagnostics) == 0


def test_program_oracle_pass_exit_code():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_EXIT_CODE,
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="exit_42")],
    )

    artifact = Artifact(
        code=RUST_EXIT_CODE_CORRECT,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.PASS


def test_program_oracle_fail_exit_code_mismatch():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_EXIT_CODE,
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="exit_mismatch")],
    )

    artifact = Artifact(
        code=RUST_EXIT_CODE_WRONG,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.FAIL
    assert len(result.diagnostics) > 0
    assert any("Exit code mismatch" in d.message for d in result.diagnostics)


def test_program_oracle_fail_output_mismatch():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_WRONG_OUTPUT,
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="output_mismatch")],
    )

    artifact = Artifact(
        code=RUST_WRONG_OUTPUT,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.FAIL
    assert len(result.diagnostics) > 0
    assert any("stdout mismatch" in d.message for d in result.diagnostics)


def test_program_oracle_not_applicable_no_sample():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    artifact = Artifact(
        code=RUST_HELLO_WORLD,
        granularity=Granularity.PROGRAM,
        sample=None,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.NOT_APPLICABLE
    assert any("No sample data" in d.message for d in result.diagnostics)


def test_program_oracle_not_applicable_no_test_cases():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_HELLO_WORLD,
        source_lang="c",
        test_cases=[],
    )

    artifact = Artifact(
        code=RUST_HELLO_WORLD,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.NOT_APPLICABLE
    assert any("No test cases" in d.message for d in result.diagnostics)


def test_program_oracle_fail_rust_compile_error():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_HELLO_WORLD,
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="compile_fail")],
    )

    invalid_rust = """
fn main() {
    println!("Missing closing quote);
}
"""

    artifact = Artifact(
        code=invalid_rust,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.verdict == Verdict.FAIL
    assert any("compilation failed" in d.message.lower() for d in result.diagnostics)


def test_program_oracle_cost_accounting():
    gcc = _gcc_path()
    rustc = _rustc_path()
    oracle = ProgramOracle(gcc_path=gcc, rustc_path=rustc)

    sample = TranslationSample(
        source_code=C_HELLO_WORLD,
        source_lang="c",
        test_cases=[
            TestCase(stdin="", test_id="test_1"),
            TestCase(stdin="", test_id="test_2"),
            TestCase(stdin="", test_id="test_3"),
        ],
    )

    artifact = Artifact(
        code=RUST_HELLO_WORLD,
        granularity=Granularity.PROGRAM,
        sample=sample,
    )

    state = ControllerState(prefix="")
    result = oracle.run(state, artifact, OracleContext())

    assert result.realized_cost == 1 + 3 * 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
