"""The week's dishes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Dish:
    name: str
    price_cents: int
