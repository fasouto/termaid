"""Data model for XY chart diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class XYDataset:
    label: str = ""
    values: list[float] = field(default_factory=list)
    chart_type: str = "bar"  # "bar" or "line"


@dataclass
class XYChart:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_categories: list[str] = field(default_factory=list)
    x_range: tuple[float, float] | None = None  # min --> max
    y_range: tuple[float, float] | None = None
    datasets: list[XYDataset] = field(default_factory=list)
    horizontal: bool = False
    warnings: list[str] = field(default_factory=list)
