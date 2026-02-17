from __future__ import annotations

from typing import cast

from core.llm_output import AssistantContent
from core.types import GenerateMessage
from feedback.strategies import UserRoundRepair


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
