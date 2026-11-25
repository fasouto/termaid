"""Parser for Mermaid gantt diagrams.

Syntax:
    gantt
        title Project Plan
        dateFormat YYYY-MM-DD
        axisFormat %b %d
        section Design
            Wireframes     :done, des1, 2024-01-01, 2024-01-14
            Prototypes     :active, des2, 2024-01-08, 2024-01-21
        section Development
            Frontend       :dev1, after des2, 30d
            Backend        :crit, dev2, 2024-01-15, 2024-03-01

Dates keep their time of day, so a chart can span years or milliseconds.
``dateFormat x`` (Unix milliseconds) and ``dateFormat X`` (Unix seconds)
are read as UTC and stored as naive datetimes, so the output never depends
on the machine's timezone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..model.gantt import Duration, Gantt, GanttSection, GanttTask, TickInterval

# Mermaid (dayjs) date format tokens -> strptime directives. SSS maps to %f,
# which right-pads three digits to microseconds.
_FORMAT_TOKENS = {
    "YYYY": "%Y", "YY": "%y",
    "MMMM": "%B", "MMM": "%b", "MM": "%m", "M": "%m",
    "DD": "%d", "D": "%d",
    "HH": "%H", "H": "%H", "hh": "%I", "h": "%I",
    "mm": "%M", "m": "%M",
    "ss": "%S", "s": "%S",
    "SSS": "%f",
    "A": "%p", "a": "%p",
}
_FORMAT_TOKEN_RE = re.compile("|".join(sorted(_FORMAT_TOKENS, key=len, reverse=True)))
_EPOCH = datetime(1970, 1, 1)

# Mermaid's grammar is ^(\d+(?:\.\d+)?)(ms|[Mdhmswy])$; the long spellings
# are kept from earlier termaid versions.
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(ms|[Mdhmswy]|days?|weeks?|months?)$")
_DURATION_UNITS = {
    "ms": "millisecond", "s": "second", "m": "minute", "h": "hour",
    "d": "day", "w": "week", "M": "month", "y": "year",
    "day": "day", "days": "day", "week": "week", "weeks": "week",
    "month": "month", "months": "month",
}
_TICK_INTERVAL_RE = re.compile(r"^([1-9][0-9]*)(millisecond|second|minute|hour|day|week|month)$")

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY = timedelta(days=1)
# A task stretched over more days than this keeps its unstretched end.
_MAX_STRETCH_DAYS = 100_000


@dataclass
class _Calendar:
    """The days ``excludes``, ``includes`` and ``weekend`` take out of a task's duration."""
    excludes: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    weekend_friday: bool = False

    def stretch(self, start: datetime, end: datetime, date_format: str) -> datetime:
        """``end`` pushed one day later for each excluded day, as Mermaid's fixTaskDates does.

        Mermaid checks the days from the one after ``start`` up to ``end``,
        moving ``end`` as it goes.
        """
        days_off = {_WEEKDAYS.index(w) for w in self.excludes if w in _WEEKDAYS}
        if "weekends" in self.excludes:
            days_off |= {4, 5} if self.weekend_friday else {5, 6}
        dates_off = self._dates(self.excludes, date_format)
        if len(days_off) == 7 or not (days_off or dates_off):
            return end
        dates_on = self._dates(self.includes, date_format)
        day = start + _DAY
        try:
            for _ in range(_MAX_STRETCH_DAYS):
                if day > end:
                    return end
                d = day.date()
                if d not in dates_on and (day.weekday() in days_off or d in dates_off):
                    end += _DAY
                day += _DAY
        except OverflowError:
            pass
        return end

    @staticmethod
    def _dates(words: list[str], date_format: str) -> set[date]:
        return {d.date() for d in (_parse_date(w, date_format) for w in words) if d is not None}


def parse_gantt(text: str) -> Gantt:
    """Parse a mermaid gantt diagram definition."""
    lines = text.strip().splitlines()
    gantt = Gantt()

    if not lines:
        return gantt

    current_section: GanttSection | None = None
    tasks: list[GanttTask] = []
    calendar = _Calendar()

    for line in lines[1:]:  # skip "gantt" header
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()

        if lower.startswith("title "):
            gantt.title = stripped[6:].strip()
            continue

        if lower.startswith("dateformat "):
            gantt.date_format = stripped[11:].strip()
            continue

        if lower.startswith("axisformat "):
            gantt.axis_format = stripped[11:].strip()
            continue

        if lower.startswith("tickinterval "):
            m = _TICK_INTERVAL_RE.match(stripped[13:].strip())
            if m:
                gantt.tick_interval = TickInterval(int(m.group(1)), m.group(2))
            continue

        if lower.startswith(("excludes ", "includes ")):
            words = [w for w in re.split(r"[\s,]+", lower[9:]) if w]
            (calendar.excludes if lower[0] == "e" else calendar.includes).extend(words)
            continue

        if lower.startswith("weekend "):
            calendar.weekend_friday = lower[8:].strip() == "friday"
            continue

        if lower.startswith("todaymarker "):
            if "off" in lower:
                gantt.today_marker = False
            continue

        # Vertical marker: vert 2024-02-15
        if lower.startswith("vert "):
            d = _parse_date(stripped[5:].strip(), gantt.date_format)
            if d:
                gantt.vertical_markers.append(d)
            continue

        if lower.startswith("section "):
            current_section = GanttSection(title=stripped[8:].strip())
            gantt.sections.append(current_section)
            continue

        # Task line: "Title :tags, id, start, end/duration"
        if ":" in stripped:
            task = _parse_task(stripped, gantt.date_format)
            if task:
                if current_section is None:
                    current_section = GanttSection(title="")
                    gantt.sections.append(current_section)

                current_section.tasks.append(task)
                tasks.append(task)

    _schedule(tasks, calendar, gantt.date_format)
    return gantt


def _schedule(tasks: list[GanttTask], calendar: _Calendar, date_format: str) -> None:
    """Give each task its start and end, the way Mermaid's compileTasks does.

    A task with neither a start date nor ``after`` starts when the task
    written before it ends, in whatever section. ``after`` and ``until`` may
    name tasks written later, so passes repeat until nothing changes. Days
    the calendar excludes stretch a duration.
    """
    by_id = {task.id: task for task in tasks}

    def known(ids: str) -> list[GanttTask]:
        return [by_id[i] for i in ids.split() if i in by_id]

    for _ in range(len(tasks) + 1):
        changed = False
        for i, task in enumerate(tasks):
            if task.start is None:
                deps = known(task.after) if task.after else tasks[i - 1:i]
                ends = [dep.end for dep in deps]
                if ends and None not in ends:
                    task.start = max(ends)
                    changed = True
            if task.start is not None and task.end is None:
                if task.until:
                    starts = [dep.start for dep in known(task.until)]
                    if starts and None not in starts:
                        task.end = min(starts)
                        changed = True
                elif task.duration is not None:
                    end = task.duration.end_from(task.start)
                    if end is not None:
                        task.end = calendar.stretch(task.start, end, date_format)
                        changed = True
        if not changed:
            break


def _parse_task(line: str, date_format: str) -> GanttTask | None:
    """Parse a task line like 'Title :done, id1, 2024-01-01, 2024-01-14'."""
    colon_idx = line.find(":")
    if colon_idx < 0:
        return None

    title = line[:colon_idx].strip()
    rest = line[colon_idx + 1:].strip()

    task = GanttTask(title=title)

    parts = [p.strip() for p in rest.split(",")]

    # Extract tags (done, active, crit, milestone)
    remaining: list[str] = []
    for part in parts:
        low = part.lower()
        if low == "done":
            task.is_done = True
        elif low == "active":
            task.is_active = True
        elif low == "crit":
            task.is_crit = True
        elif low == "milestone":
            task.is_milestone = True
        else:
            remaining.append(part)

    # Parse remaining: [id], [start|after X], [end|duration]
    for part in remaining:
        if part.lower().startswith("after "):
            # Support multiple: "after task1 task2" - store all IDs
            task.after = part[6:].strip()
            continue
        if part.lower().startswith("until "):
            task.until = part[6:].strip()
            continue

        d = _parse_date(part, date_format)
        if d:
            if task.start is None and not task.after:
                task.start = d
            else:
                task.end = d
            continue

        dur = _parse_duration(part)
        if dur is not None:
            task.duration = dur
            continue

        # Must be an ID
        if not task.id and re.match(r'^[a-zA-Z_]\w*$', part):
            task.id = part

    # Auto-generate ID if missing
    if not task.id:
        task.id = re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:20]

    return task


def _parse_date(text: str, date_format: str) -> datetime | None:
    """Parse a date string, honoring the diagram's dateFormat directive."""
    text = text.strip()
    fmt = date_format.strip()
    if fmt in ("x", "X"):
        try:
            value = float(text)
        except ValueError:
            return None
        try:
            return _EPOCH + (timedelta(milliseconds=value) if fmt == "x" else timedelta(seconds=value))
        except (OverflowError, ValueError):  # past year 9999, or nan
            return None
    # Try the declared dateFormat first (Mermaid/dayjs tokens)
    if fmt:
        try:
            return datetime.strptime(text, _FORMAT_TOKEN_RE.sub(lambda m: _FORMAT_TOKENS[m.group(0)], fmt))
        except (ValueError, re.error):
            # re.error: a format naming one field twice, such as MM/DD/MM.
            pass
    # Try ISO format
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # Try MM/DD/YYYY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def _parse_duration(text: str) -> Duration | None:
    """Parse a duration like '30d', '2w', '1.5h', '406ms'; units are case-sensitive."""
    m = _DURATION_RE.match(text.strip())
    if not m:
        return None
    return Duration(float(m.group(1)), _DURATION_UNITS[m.group(2)])
