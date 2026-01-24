from __future__ import annotations

from core.llm_output import FenceState, FenceTracker


def test_fence_tracker_tracks_inside_and_output() -> None:
    tracker = FenceTracker(allowed_langs=("rust", "rs"))

    assert tracker.state == FenceState.OUTSIDE
    assert tracker.feed("preamble;\n") == ""
    assert tracker.consume_inside() == ""

    assert tracker.feed("```rust\n") == ""
    assert tracker.state == FenceState.INSIDE

    assert tracker.feed("let x = 1;\n") == "let x = 1;\n"
    assert tracker.consume_inside() == "let x = 1;\n"
    assert tracker.consume_inside() == ""

    assert tracker.feed("let y = 2;\n") == "let y = 2;\n"
    assert tracker.consume_inside() == "let y = 2;\n"

    assert tracker.feed("```\n") == ""
    assert tracker.state == FenceState.DONE
    assert tracker.feed("after\n") == ""
