from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Budget:
    gen_tokens_budget: int
    gen_tokens_used: int = 0
    oracle_calls: dict[str, int] = field(default_factory=dict)
    oracle_budget: dict[str, int] = field(default_factory=dict)

    def can_spend_tokens(self, amount: int) -> bool:
        return self.gen_tokens_used + amount <= self.gen_tokens_budget

    def add_tokens(self, amount: int) -> None:
        self.gen_tokens_used += max(0, amount)

    def record_oracle_call(self, oracle_name: str, cost: int = 1) -> None:
        self.oracle_calls[oracle_name] = self.oracle_calls.get(oracle_name, 0) + 1
        self.oracle_budget[oracle_name] = self.oracle_budget.get(oracle_name, 0) + cost

    def snapshot(self) -> dict[str, int]:
        return {
            "gen_tokens_used": self.gen_tokens_used,
            "gen_tokens_budget": self.gen_tokens_budget,
            "oracle_calls_total": sum(self.oracle_calls.values()),
        }
