from __future__ import annotations

from core.llm_output import FenceState, RustFenceExtractor


def test_no_fence_yields_no_output() -> None:
    extractor = RustFenceExtractor()
    assert extractor.feed('''header
''') == ""
    assert extractor.feed('''still outside''') == ""
    assert extractor.state == FenceState.OUTSIDE


def test_extract_code_after_opening_fence() -> None:
    extractor = RustFenceExtractor()
    assert extractor.feed('''preface
```rust
line1\n''') == "line1\n"
    assert extractor.feed('''line2\n''') == "line2\n"


def test_stop_after_closing_fence() -> None:
    extractor = RustFenceExtractor()
    chunk = '''```rs
line1
line2
```
trailing
'''
    assert extractor.feed(chunk) == '''line1
line2
'''
    assert extractor.feed('''more\n''') == ""
    assert extractor.state == FenceState.DONE


def test_split_fence_tokens() -> None:
    extractor = RustFenceExtractor()
    assert extractor.feed('''`''') == ""
    assert extractor.feed('''``ru''') == ""
    assert extractor.feed('''st
code''') == "code"


def test_non_rust_fence_ignored() -> None:
    extractor = RustFenceExtractor()
    assert extractor.feed('''```python
print('x')
```
''') == ""
