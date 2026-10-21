"""The week's order of one member — placed and changed until the kitchen buys its ingredients."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Order:
    member: str
    dishes: list[str] = field(default_factory=list)

    def add(self, dish: str) -> None:
        self.dishes.append(dish)
