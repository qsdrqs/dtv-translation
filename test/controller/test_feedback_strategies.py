from __future__ import annotations

from core.types import GenerateMessage
from feedback.strategies import AppendToLastAssistant


def test_append_to_last_assistant_keeps_prefix_when_feedback_empty() -> None:
    messages = [GenerateMessage(role="assistant", content="let x = 1;", stop=False)]
    strategy = AppendToLastAssistant()

    updated = strategy.apply(messages, "", "let x = 1;")

    assert len(updated) == 1
    assert isinstance(updated[0], GenerateMessage)
    assert updated[0].content == "let x = 1;"
