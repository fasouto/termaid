"""Data model for gantt diagrams.

Instants are naive datetimes: a day-based chart holds midnights, a chart
with ``dateFormat x`` holds UTC wall-clock times. The chart's time span is
whatever its tasks cover, so bars, markers and ticks all scale from the same
two instants whether the span is years or milliseconds.
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

_FIXED_UNITS = {
    "millisecond": timedelta(milliseconds=1),
    "second": timedelta(seconds=1),
    "minute": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
}


def shift(dt: datetime, amount: float, unit: str) -> datetime:
    """Move ``dt`` by ``amount`` units the way dayjs ``add`` does.

    Months and years step the calendar (truncating a fractional amount and
    clamping the day to the target month's length), days and weeks round to
    whole days, and the smaller units are exact.
    """
    if unit in ("month", "year"):
        months = int(amount) * (12 if unit == "year" else 1)
        year, month0 = divmod(dt.year * 12 + dt.month - 1 + months, 12)
        day = min(dt.day, calendar.monthrange(year, month0 + 1)[1])
        return dt.replace(year=year, month=month0 + 1, day=day)
    if unit in ("day", "week"):
        days = amount * (7 if unit == "week" else 1)
        return dt + timedelta(days=math.floor(days + 0.5))
    return dt + _FIXED_UNITS[unit] * amount


@dataclass(frozen=True)
class Duration:
    amount: float
    unit: str

    def end_from(self, start: datetime) -> datetime:
        return shift(start, self.amount, self.unit)


@dataclass(frozen=True)
class TickInterval:
    count: int
    unit: str


@dataclass
class GanttTask:
    id: str = ""
    title: str = ""
    start: datetime | None = None
    end: datetime | None = None
    duration: Duration | None = None  # applied to start once it is known
    is_done: bool = False
    is_active: bool = False
    is_crit: bool = False
    is_milestone: bool = False
    after: str = ""  # task ID dependency

    def start_at(self, start: datetime) -> None:
        self.start = start
        if self.end is None and self.duration is not None:
            self.end = self.duration.end_from(start)


@dataclass
class GanttSection:
    title: str
    tasks: list[GanttTask] = field(default_factory=list)


@dataclass
class Gantt:
    title: str = ""
    date_format: str = "YYYY-MM-DD"
    axis_format: str | None = None  # d3 time-format string
    tick_interval: TickInterval | None = None
    sections: list[GanttSection] = field(default_factory=list)
    vertical_markers: list[datetime] = field(default_factory=list)
    today_marker: bool = True
    warnings: list[str] = field(default_factory=list)

    def time_range(self) -> tuple[datetime, datetime] | None:
        """Earliest start and latest end over all tasks, or None without both."""
        tasks = [t for s in self.sections for t in s.tasks]
        starts = [t.start for t in tasks if t.start is not None]
        ends = [t.end for t in tasks if t.end is not None]
        if not starts or not ends:
            return None
        return min(starts), max(ends)
