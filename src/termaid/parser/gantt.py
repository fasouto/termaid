"""Parser for Mermaid gantt diagrams.

Syntax:
    gantt
        title Project Plan
        dateFormat YYYY-MM-DD
        section Design
            Wireframes     :done, des1, 2024-01-01, 2024-01-14
            Prototypes     :active, des2, 2024-01-08, 2024-01-21
        section Development
            Frontend       :dev1, after des2, 30d
            Backend        :crit, dev2, 2024-01-15, 2024-03-01
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from ..model.gantt import Gantt, GanttSection, GanttTask


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

        if lower.startswith("axisformat ") or lower.startswith("excludes ") or lower.startswith("tickinterval ") or lower.startswith("weekend "):
            continue  # skip formatting directives

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
            task = _parse_task(stripped, tasks_by_id, gantt.date_format)
            if task:
                if current_section is None:
                    current_section = GanttSection(title="")
                    gantt.sections.append(current_section)

                # Auto-chain: if no start and no after, start after the previous task
                if task.start is None and not task.after and current_section.tasks:
                    prev = current_section.tasks[-1]
                    if prev.end:
                        task.start = prev.end
                        if task.end is None and hasattr(task, '_duration_days'):
                            task.end = task.start + timedelta(days=task._duration_days)

                current_section.tasks.append(task)
                if task.id:
                    tasks_by_id[task.id] = task

    # Resolve "after" dependencies (multiple passes for chains)
    for _ in range(len(tasks_by_id) + 1):
        changed = False
        for section in gantt.sections:
            for task in section.tasks:
                if task.after and task.start is None:
                    # Multiple IDs: "after task1 task2" - use latest end date
                    after_ids = task.after.split()
                    latest_end: date | None = None
                    all_resolved = True
                    for aid in after_ids:
                        dep = tasks_by_id.get(aid)
                        if dep and dep.end:
                            if latest_end is None or dep.end > latest_end:
                                latest_end = dep.end
                        else:
                            all_resolved = False
                    if all_resolved and latest_end:
                        task.start = latest_end
                        if task.end is None and hasattr(task, '_duration_days'):
                            task.end = task.start + timedelta(days=task._duration_days)
                        changed = True
        if not changed:
            break

    return gantt


def _parse_task(line: str, tasks_by_id: dict[str, GanttTask], date_format: str) -> GanttTask | None:
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
    for i, part in enumerate(remaining):
        low = part.lower()

        if low.startswith("after "):
            # Support multiple: "after task1 task2" - store all IDs
            task.after = part[6:].strip()
            continue

        # Try as duration (e.g., "30d", "2w")
        dur = _parse_duration(part)
        if dur is not None:
            task._duration_days = dur  # type: ignore[attr-defined]
            if task.start:
                task.end = task.start + timedelta(days=dur)
            continue

        # Try as date
        d = _parse_date(part, date_format)
        if d:
            if task.start is None:
                task.start = d
            else:
                task.end = d
            continue

        # Must be an ID
        if not task.id and re.match(r'^[a-zA-Z_]\w*$', part):
            task.id = part

    # Auto-generate ID if missing
    if not task.id:
        task.id = re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:20]

    return task


def _parse_date(text: str, date_format: str) -> date | None:
    """Parse a date string."""
    text = text.strip()
    # Try ISO format first
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # Try MM/DD/YYYY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def _parse_duration(text: str) -> int | None:
    """Parse a duration like '30d', '2w', '3m'."""
    text = text.strip().lower()
    m = re.match(r'^(\d+)\s*(d|day|days|w|week|weeks|m|month|months)$', text)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)[0]
    if unit == 'd':
        return val
    elif unit == 'w':
        return val * 7
    elif unit == 'm':
        return val * 30
    return None
