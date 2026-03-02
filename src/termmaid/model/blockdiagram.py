"""Data model for block diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    id: str
    label: str = ""
    shape: str = "rectangle"
    col_span: int = 1
    is_space: bool = False
    children: list[Block] = field(default_factory=list)
    columns: int = 0  # for nested groups (0 = inherit)


@dataclass
class BlockLink:
    source: str
    target: str
    label: str = ""


@dataclass
class BlockDiagram:
    blocks: list[Block] = field(default_factory=list)
    links: list[BlockLink] = field(default_factory=list)
    columns: int = 0  # 0 = auto
