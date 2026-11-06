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
from datetime import datetime, timedelta

from ..model.gantt import Duration, Gantt, GanttSection, GanttTask, TickInterval

# Mermaid (dayjs) date format tokens -> strptime directives. SSS maps to %f,
# which right-pads three digits to microseconds.
_FORMAT_TOKENS = {
    "YYYY": "%Y", "YY": "%y",
    "MM": "%m", "M": "%m",
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


def parse_gantt(text: str) -> Gantt:
    """Parse a mermaid gantt diagram definition."""
    lines = text.strip().splitlines()
    gantt = Gantt()

    if not lines:
        return gantt

    current_section: GanttSection | None = None
    tasks_by_id: dict[str, GanttTask] = {}

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

        if lower.startswith("excludes ") or lower.startswith("weekend "):
            continue  # exclusions are not applied

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

                # Auto-chain: if no start and no after, start after the previous task
                if task.start is None and not task.after and current_section.tasks:
                    prev = current_section.tasks[-1]
                    if prev.end:
                        task.start_at(prev.end)

                current_section.tasks.append(task)
                if task.id:
                    tasks_by_id[task.id] = task

    # Resolve "after" dependencies (multiple passes for chains)
    for _ in range(len(tasks_by_id) + 1):
        changed = False
        for section in gantt.sections:
            for task in section.tasks:
                if not task.after or task.start is not None:
                    continue
                # Multiple IDs: "after task1 task2" - start at the latest end
                deps = [tasks_by_id.get(aid) for aid in task.after.split()]
                ends = [dep.end for dep in deps if dep is not None and dep.end is not None]
                if len(ends) == len(deps):
                    task.start_at(max(ends))
                    changed = True
        if not changed:
            break

    return gantt


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
            if task.start:
                task.end = dur.end_from(task.start)
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
        return _EPOCH + (timedelta(milliseconds=value) if fmt == "x" else timedelta(seconds=value))
    # Try the declared dateFormat first (Mermaid/dayjs tokens)
    if fmt:
        try:
            return datetime.strptime(text, _FORMAT_TOKEN_RE.sub(lambda m: _FORMAT_TOKENS[m.group(0)], fmt))
        except ValueError:
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
