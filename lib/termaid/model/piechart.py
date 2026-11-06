"""Data model for pie chart diagrams (rendered as bar charts)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PieSlice:
    label: str
    value: float


@dataclass
class PieChart:
    title: str = ""
    show_data: bool = False
    slices: list[PieSlice] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
