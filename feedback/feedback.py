from __future__ import annotations

from dataclasses import dataclass, field

from core.types import OracleOutput


@dataclass
class FeedbackState:
    """Stores recent oracle diagnostics for prompt augmentation."""
    max_items: int = 8  # Cap on stored messages.
    items: list[str] = field(default_factory=list)

    def update(self, outputs: list[OracleOutput]) -> None:
        for output in outputs:
            for diag in output.diagnostics:
                msg = f"[{output.oracle_name}] {diag.message}"
                if msg in self.items:
                    self.items.remove(msg)
                self.items.append(msg)
        if len(self.items) > self.max_items:
            self.items = self.items[-self.max_items :]

    def encode(self) -> str:
        if not self.items:
            return ""
        return "\n".join(self.items)

    def augment_prompt(self, base_prompt: str) -> str:
        feedback = self.encode()
        if not feedback:
            return base_prompt
        return f"{base_prompt}\n\n# Feedback\n{feedback}\n"
