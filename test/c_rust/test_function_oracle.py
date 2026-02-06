from __future__ import annotations

import json
from pathlib import Path

from c_rust.oracles.function_diff_test_oracle.function_oracle import FunctionOracle
from core.types import Artifact, ControllerState, OracleContext, TestCase, TranslationSample, Verdict
from test.c_rust.utils import _gcc_path, _rustc_path


def _load_trap_fixture() -> tuple[TranslationSample, str]:
    base_dir = Path(__file__).resolve().parents[0] / "fixture" / "function"
    c_program = (base_dir / "trap_c_source.c").read_text(encoding="utf-8").strip()
    rust_code = (base_dir / "trap_rs.rs").read_text(encoding="utf-8")
    raw = json.loads((base_dir / "trap_tests.json").read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("tests", [])
    cases = [TestCase(stdin=item["stdin"], test_id=item.get("test_id")) for item in raw]
    sample = TranslationSample(source_code=c_program, source_lang="c", test_cases=cases)
    return sample, rust_code


def _load_rename_fixture() -> tuple[TranslationSample, str]:
    base_dir = Path(__file__).resolve().parents[0] / "fixture" / "function"
    c_program = (base_dir / "rename_c_source.c").read_text(encoding="utf-8").strip()
    rust_code = (base_dir / "rename_rs.rs").read_text(encoding="utf-8")
    raw = json.loads((base_dir / "rename_tests.json").read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("tests", [])
    cases = [TestCase(stdin=item["stdin"], test_id=item.get("test_id")) for item in raw]
    sample = TranslationSample(source_code=c_program, source_lang="c", test_cases=cases)
    return sample, rust_code

def _load_rename_ffi_fixture() -> tuple[TranslationSample, str]:
    base_dir = Path(__file__).resolve().parents[0] / "fixture" / "function"
    c_program = (base_dir / "rename_ffi_c_source.c").read_text(encoding="utf-8").strip()
    rust_code = (base_dir / "rename_ffi_rs.rs").read_text(encoding="utf-8")
    raw = json.loads((base_dir / "rename_ffi_tests.json").read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("tests", [])
    cases = [TestCase(stdin=item["stdin"], test_id=item.get("test_id")) for item in raw]
    sample = TranslationSample(source_code=c_program, source_lang="c", test_cases=cases)
    return sample, rust_code


def test_function_oracle_passes_on_trap_fixture() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    sample, rust_code = _load_trap_fixture()
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="trap")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.PASS


def test_function_oracle_c_name_ambiguous_not_applicable() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    c_source = "int foo_bar(){return 0;} int foobar(){return 1;}"
    rust_code = "fn dummy() {}"
    sample = TranslationSample(
        source_code=c_source,
        source_lang="c",
        test_cases=[TestCase(stdin="0\n", test_id="t1")],
    )
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="fooBar")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.NOT_APPLICABLE
    assert any("C function name ambiguous" in d.message for d in result.diagnostics)


def test_function_oracle_rust_name_ambiguous_not_applicable() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    c_source = "int fooBar(int x){return x;}"
    rust_code = "fn foo_bar(x: i32) -> i32 { x }\nfn foobar(x: i32) -> i32 { x }"
    sample = TranslationSample(
        source_code=c_source,
        source_lang="c",
        test_cases=[TestCase(stdin="0\n", test_id="t1")],
    )
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="fooBar")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.NOT_APPLICABLE
    assert any("Rust function name ambiguous" in d.message for d in result.diagnostics)


def test_function_oracle_exact_match_beats_normalized_ambiguity() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    c_source = "int foo_bar(){return 0;} int foobar(){return 1;}"
    rust_code = "fn nothing() {}"
    sample = TranslationSample(
        source_code=c_source,
        source_lang="c",
        test_cases=[TestCase(stdin="0\n", test_id="t1")],
    )
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="foo_bar")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.NOT_APPLICABLE
    assert any("Rust function not found" in d.message for d in result.diagnostics)
    assert not any("C function name ambiguous" in d.message for d in result.diagnostics)


def test_function_oracle_static_c_function_not_applicable() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    c_source = "static int f(int x){return x;}"
    rust_code = "fn f(x: i32) -> i32 { x }"
    sample = TranslationSample(
        source_code=c_source,
        source_lang="c",
        test_cases=[TestCase(stdin="0\n", test_id="t1")],
    )
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="f")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.NOT_APPLICABLE
    assert any("C function is static" in d.message for d in result.diagnostics)


def test_function_oracle_signature_incompatible_not_applicable() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    c_source = "int f(int x){return x;}"
    rust_code = "fn f(x: i32) -> i64 { x as i64 }"
    sample = TranslationSample(
        source_code=c_source,
        source_lang="c",
        test_cases=[TestCase(stdin="0\n", test_id="t1")],
    )
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="f")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.NOT_APPLICABLE
    assert any("return_value_mismatch" in d.message for d in result.diagnostics)


def test_function_oracle_handles_renamed_function() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    sample, rust_code = _load_rename_fixture()
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="singleFunction")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.PASS

def test_function_oracle_accepts_rust_name_in_context() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    sample, rust_code = _load_rename_fixture()
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="single_function")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.PASS


def test_function_oracle_rename_with_ffi_bridge() -> None:
    gcc = _gcc_path()
    rustc = _rustc_path()
    sample, rust_code = _load_rename_ffi_fixture()
    oracle = FunctionOracle(gcc_path=gcc, rustc_path=rustc)
    artifact = Artifact(code=rust_code, sample=sample)
    state = ControllerState(prefix=rust_code)
    context = OracleContext(closed_function_name="addOffset")

    result = oracle.run(state, artifact, context)

    assert result.verdict == Verdict.PASS, (
        f"expected PASS but got {result.verdict}: "
        f"{[d.message for d in result.diagnostics]}"
    )
