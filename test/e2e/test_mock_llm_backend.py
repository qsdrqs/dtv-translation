from __future__ import annotations

from pathlib import Path

import pytest
import torch

from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.llm_output import WriteRegionParser
from core.types import GenerateContext, GenerateMessage
from test.e2e.mock_llm_backend import MockLLMBackend


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _collect_boundaries(text: str, source_path: Path) -> list[int]:
    MockLLMBackend.configure(source_path=source_path, chunk_size=1)
    backend = MockLLMBackend(
        model_name="mock",
        stop_criteria_factory=lambda tok: [DTVStoppingCriteria(tok, RUST_PROFILE)],
    )
    context = GenerateContext(messages=(), steps=0, max_new_length=1024, extract_write_region=False)

    boundaries: list[int] = []
    pos = 0
    while pos < len(text):
        result = backend.generate_step(context)
        if result.delta_text:
            expected = text[pos : pos + len(result.delta_text)]
            assert result.delta_text == expected
            pos += len(result.delta_text)
        if result.stop_reason.kind == "boundary":
            trimmed = text[:pos].rstrip()
            if trimmed:
                boundaries.append(len(trimmed) - 1)
        if result.stop_reason.kind == "eos":
            break
        if not result.delta_text:
            break
    return boundaries


def test_streaming_emits_full_content(tmp_path: Path) -> None:
    source_path = tmp_path / "template.md"
    _write(source_path, "abcd")

    MockLLMBackend.configure(source_path=source_path, chunk_size=1)
    backend = MockLLMBackend(model_name="mock")
    context = GenerateContext(messages=(), steps=0, max_new_length=1024, extract_write_region=False)

    result = backend.generate_step(context)

    assert result.delta_text == "abcd"
    assert result.delta_tokens == 4
    assert result.stop_reason.kind == "eos"


def test_streaming_with_messages_preserves_output(tmp_path: Path) -> None:
    source_path = tmp_path / "template.md"
    _write(source_path, "hi")

    MockLLMBackend.configure(source_path=source_path, chunk_size=1)
    backend = MockLLMBackend(model_name="mock")
    messages = (
        GenerateMessage(role="user", content="Translate:", stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    )
    context = GenerateContext(messages=messages, steps=0, max_new_length=1024, extract_write_region=False)

    result = backend.generate_step(context)

    assert result.delta_text == "hi"
    assert result.stop_reason.kind == "eos"


def test_stop_criteria_factory_triggers_boundary(tmp_path: Path) -> None:
    class _StopAfter:
        def __init__(self, limit: int) -> None:
            self.limit = limit

        def set_prompt_token_count(self, prompt_token_count: int) -> None:
            _ = prompt_token_count

        def __call__(self, input_ids, scores, **kwargs):
            _ = scores
            _ = kwargs
            return torch.tensor([input_ids.shape[-1] >= self.limit], dtype=torch.bool)

    source_path = tmp_path / "template.md"
    _write(source_path, "abcd")

    MockLLMBackend.configure(source_path=source_path, chunk_size=1)
    backend = MockLLMBackend(
        model_name="mock",
        stop_criteria_factory=lambda tok: [_StopAfter(2)],
    )
    context = GenerateContext(messages=(), steps=0, max_new_length=1024, extract_write_region=False)

    result = backend.generate_step(context)

    assert result.delta_text == "ab"
    assert result.stop_reason.kind == "boundary"


def test_stop_criteria_semicolon_ignores_line_comment(tmp_path: Path) -> None:
    text = "// comment;\nlet x = 1;\n"
    source_path = tmp_path / "template.txt"
    _write(source_path, text)

    boundaries = _collect_boundaries(text, source_path)

    assert boundaries == [text.rfind(";")]


def test_stop_criteria_block_comment_ignores_brace(tmp_path: Path) -> None:
    text = "/* } */\nfn main() {\n}\n"
    source_path = tmp_path / "template.txt"
    _write(source_path, text)

    boundaries = _collect_boundaries(text, source_path)

    assert boundaries == [text.rfind("}")]


def test_stop_criteria_tracks_prompt_after_parser_restore(tmp_path: Path) -> None:
    text = (
        "Here is the translated Rust code for the provided C code snippet:\n\n"
        "<<BEGIN_WRITE_CODE>>\n"
        "use std::io::{self, Read};\n"
        "fn main() {\n"
        "    let value = 1;\n"
        "    println!(\"{value}\");\n"
        "}\n"
        "<<END_WRITE_CODE>>\n"
    )
    source_path = tmp_path / "template.md"
    _write(source_path, text)

    MockLLMBackend.configure(source_path=source_path, chunk_size=1)
    write_region_parser = WriteRegionParser()
    backend = MockLLMBackend(
        model_name="mock",
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE, write_region_parser=write_region_parser)
        ],
    )
    context = GenerateContext(messages=(), steps=0, max_new_length=1024, extract_write_region=False)

    first = backend.generate_step(context)
    snapshot = write_region_parser.capture()
    write_region_parser.restore(snapshot)
    second = backend.generate_step(context)

    assert first.stop_reason.kind == "boundary"
    assert first.delta_text
    assert second.delta_text

def test_c_to_rust_translate_trap() -> None:
    base_dir = Path(__file__).resolve().parent / "c2rust" / "trap"
    c_source_path = base_dir / "trap_c_source.c"
    source_path = base_dir / "llm_output.md"

    c_program = c_source_path.read_text(encoding="utf-8").strip()
    prompt = (
        "Translate the following C code into Rust, keep the same function order:\n"
        "```c\n"
        f"{c_program}\n"
        "```\n"
    )

    source_text = source_path.read_text(encoding="utf-8")
    MockLLMBackend.configure(source_path=source_path, chunk_size=1)
    backend = MockLLMBackend(
        model_name="mock",
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE)
        ],
    )
    messages = (
        GenerateMessage(role="user", content=prompt, stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    )
    context = GenerateContext(messages=messages, steps=0, max_new_length=4096, extract_write_region=False)

    chunks: list[str] = []
    pos = 0
    while pos < len(source_text):
        result = backend.generate_step(context)
        if not result.delta_text:
            assert result.stop_reason.kind == "eos"
            break
        expected = source_text[pos : pos + len(result.delta_text)]
        assert result.delta_text == expected
        chunks.append(result.delta_text)
        pos += len(result.delta_text)
        if result.stop_reason.kind == "eos":
            break

    print('\n-----------------------------------'.join(chunks))
    assert "".join(chunks) == source_text
