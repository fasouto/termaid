"""Data model for treemap diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreemapNode:
    label: str
    value: float = 0
    children: list[TreemapNode] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        """Total value: own value for leaves, sum of children for sections."""
        if self.children:
            return sum(c.total_value for c in self.children)
        return self.value


@dataclass
class Treemap:
    roots: list[TreemapNode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        return sum(r.total_value for r in self.roots)
