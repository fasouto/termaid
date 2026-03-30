"""Data model for gantt diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class GanttTask:
    id: str = ""
    title: str = ""
    start: date | None = None
    end: date | None = None
    is_done: bool = False
    is_active: bool = False
    is_crit: bool = False
    is_milestone: bool = False
    after: str = ""  # task ID dependency

    @property
    def duration_days(self) -> int:
        if self.start and self.end:
            return (self.end - self.start).days
        return 0


@dataclass
class GanttSection:
    title: str
    tasks: list[GanttTask] = field(default_factory=list)


@dataclass
class Gantt:
    title: str = ""
    date_format: str = "YYYY-MM-DD"
    sections: list[GanttSection] = field(default_factory=list)
    vertical_markers: list[date] = field(default_factory=list)
    today_marker: bool = True
    warnings: list[str] = field(default_factory=list)
