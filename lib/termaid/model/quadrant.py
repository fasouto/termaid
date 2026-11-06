"""Data model for quadrant chart diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QuadrantPoint:
    label: str
    x: float  # 0.0 to 1.0
    y: float  # 0.0 to 1.0


@dataclass
class QuadrantChart:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    quadrant_1: str = "Q1"  # top-right
    quadrant_2: str = "Q2"  # top-left
    quadrant_3: str = "Q3"  # bottom-left
    quadrant_4: str = "Q4"  # bottom-right
    points: list[QuadrantPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
