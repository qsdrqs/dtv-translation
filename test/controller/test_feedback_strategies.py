from __future__ import annotations

from typing import cast

from core.llm_output import AssistantContent
from core.types import GenerateMessage
from feedback.strategies import AssistantInlineRepair, UserRoundRepair


def test_assistant_inline_repair_places_feedback_in_assistant_round() -> None:
    messages = [
        GenerateMessage(role="user", content="Translate this program.", stop=True),
        GenerateMessage(role="assistant", content="```rust\nfn main() {\n", stop=False),
    ]
    strategy = AssistantInlineRepair()

    updated = strategy.apply(messages, "repair-instruction", "```rust\nfn main() {\n")
    generated = cast(list[GenerateMessage], updated)

    assert generated[-1].role == "assistant"
    assert generated[-1].stop is False
    assert "repair-instruction" in str(generated[-1].content)


def test_user_round_repair_closes_assistant_and_starts_new_turn() -> None:
    messages = [
        GenerateMessage(role="user", content="Translate this program.", stop=True),
        GenerateMessage(role="assistant", content="```rust\nfn main() {\n", stop=False),
    ]
    strategy = UserRoundRepair()

    updated = strategy.apply(messages, "repair-instruction", "```rust\nfn main() {\n")
    generated = cast(list[GenerateMessage], updated)

    assert [msg.role for msg in generated] == ["user", "assistant", "user", "assistant"]
    assert [msg.stop for msg in generated] == [True, True, True, False]
    assert generated[1].content == "```rust\nfn main() {\n"
    assert generated[2].content == "repair-instruction"
    assert generated[3].content == AssistantContent.empty()


def test_user_round_repair_adds_assistant_when_missing() -> None:
    messages = [GenerateMessage(role="user", content="Translate this program.", stop=True)]
    strategy = UserRoundRepair()

    updated = strategy.apply(messages, "repair-instruction", "```rust\n")
    generated = cast(list[GenerateMessage], updated)

    assert [msg.role for msg in generated] == ["user", "assistant", "user", "assistant"]
    assert [msg.stop for msg in generated] == [True, True, True, False]
    assert generated[1].content == "```rust\n"
    assert generated[2].content == "repair-instruction"
