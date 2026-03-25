"""Data model for mindmap diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MindmapNode:
    label: str
    children: list[MindmapNode] = field(default_factory=list)

    @property
    def depth(self) -> int:
        """Maximum depth of this subtree."""
        if not self.children:
            return 0
        return 1 + max(c.depth for c in self.children)


@dataclass
class Mindmap:
    root: MindmapNode | None = None
    warnings: list[str] = field(default_factory=list)
