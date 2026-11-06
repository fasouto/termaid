"""Renderer for gantt chart diagrams.

Renders a horizontal bar chart with tasks along the y-axis and time along
the x-axis. Tasks are grouped by sections. Every bar, marker and tick is
placed by its fraction of the chart's time span, so the same code serves a
chart that spans years and one that spans milliseconds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..model.gantt import Gantt, TickInterval, shift
from ..utils import display_width, truncate_to_width
from .canvas import Canvas


_DEFAULT_WIDTH = 80
_BAR_CHAR = "█"
_ACTIVE_CHAR = "▓"
_DONE_CHAR = "░"
_CRIT_CHAR = "█"
_MILESTONE_CHAR = "◆"

# termaid's default axis labels; Mermaid's own default is %Y-%m-%d.
_DEFAULT_AXIS_FORMAT = "%b %d"
_EPOCH = datetime(1970, 1, 1)
# d3 time-format directives that strftime lacks.
_D3_ONLY = {
    "%L": lambda t: f"{t.microsecond // 1000:03d}",
    "%Q": lambda t: str(int((t - _EPOCH) / timedelta(milliseconds=1))),
    "%s": lambda t: str(int((t - _EPOCH).total_seconds())),
    "%q": lambda t: str((t.month - 1) // 3 + 1),
}
_DIRECTIVE_RE = re.compile(r"%[-_0]?[A-Za-z%]")

# Default ticks fall on whole units: days when the chart spans at least a
# day, otherwise the largest unit that fits twice.
_SUB_DAY_UNITS = (
    timedelta(hours=1),
    timedelta(minutes=1),
    timedelta(seconds=1),
    timedelta(milliseconds=100),
    timedelta(milliseconds=10),
    timedelta(milliseconds=1),
)

# tickInterval follows d3's interval.every: a tick on every instant whose
# unit field is a multiple of the count, counting from the unit's floor.
_FIRST_SUNDAY = datetime(1970, 1, 4)
_TICK_FIELDS = {
    "millisecond": lambda t: t.microsecond // 1000,
    "second": lambda t: t.second,
    "minute": lambda t: t.minute,
    "hour": lambda t: t.hour,
    "day": lambda t: t.day - 1,
    "week": lambda t: (t - _FIRST_SUNDAY).days // 7 + 1,
    "month": lambda t: t.month - 1,
}
_TICK_FLOORS = {
    "millisecond": lambda t: t.replace(microsecond=t.microsecond // 1000 * 1000),
    "second": lambda t: t.replace(microsecond=0),
    "minute": lambda t: t.replace(second=0, microsecond=0),
    "hour": lambda t: t.replace(minute=0, second=0, microsecond=0),
    "day": lambda t: _midnight(t),
    "week": lambda t: _midnight(t) - timedelta(days=(t.weekday() + 1) % 7),
    "month": lambda t: _midnight(t).replace(day=1),
}
_TICK_UNIT_MIN_LENGTH = {
    "millisecond": timedelta(milliseconds=1),
    "second": timedelta(seconds=1),
    "minute": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=28),
}
_MAX_TICK_CANDIDATES = 10_000


def format_time(t: datetime, fmt: str) -> str:
    """Format ``t`` with a d3 time-format string such as ``%H:%M`` or ``%S.%L``."""
    def directive(m: re.Match[str]) -> str:
        special = _D3_ONLY.get(m.group(0))
        return special(t) if special else t.strftime(m.group(0))
    return _DIRECTIVE_RE.sub(directive, fmt)


def _midnight(t: datetime) -> datetime:
    return t.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class _Scale:
    """Maps instants in [start, end] onto the chart's columns."""
    start: datetime
    end: datetime
    x0: int  # first chart column
    cells: int  # columns the span is spread over

    @property
    def span(self) -> timedelta:
        return self.end - self.start

    def covers(self, t: datetime) -> bool:
        return self.start <= t <= self.end

    def col(self, t: datetime) -> int:
        return self.x0 + int((t - self.start).total_seconds() / self.span.total_seconds() * self.cells)


def _default_ticks(scale: _Scale, chart_w: int, fmt: str) -> list[tuple[int, str]]:
    """Up to seven evenly spaced ticks labelled with whole-unit instants."""
    unit = timedelta(days=1)
    if scale.span < unit:
        unit = next((u for u in _SUB_DAY_UNITS if scale.span >= 2 * u), _SUB_DAY_UNITS[-1])
    total_units = scale.span / unit
    n_ticks = max(2, min(6, int(total_units)))
    return [
        (
            scale.x0 + int(i / n_ticks * (chart_w - 2)),
            format_time(scale.start + unit * int(i / n_ticks * total_units), fmt),
        )
        for i in range(n_ticks + 1)
    ]


def _interval_ticks(scale: _Scale, interval: TickInterval, fmt: str) -> list[tuple[int, str]] | None:
    """Ticks every ``interval``, or None when they would be denser than the columns."""
    if scale.span / _TICK_UNIT_MIN_LENGTH[interval.unit] > _MAX_TICK_CANDIDATES:
        return None
    field = _TICK_FIELDS[interval.unit]
    last_col = scale.x0 + scale.cells - 1  # the span's end maps one past the axis
    ticks: list[tuple[int, str]] = []
    t = _TICK_FLOORS[interval.unit](scale.start)
    while t <= scale.end:
        if t >= scale.start and field(t) % interval.count == 0:
            ticks.append((min(scale.col(t), last_col), format_time(t, fmt)))
        t = shift(t, 1, interval.unit)
    return ticks if len(ticks) <= scale.cells else None


def render_gantt(
    diagram: Gantt,
    *,
    use_ascii: bool = False,
    width: int = _DEFAULT_WIDTH,
) -> Canvas:
    """Render a Gantt model to a Canvas."""
    if not diagram.sections:
        return Canvas(1, 1)

    bar_char = "#" if use_ascii else _BAR_CHAR
    active_char = "=" if use_ascii else _ACTIVE_CHAR
    done_char = "." if use_ascii else _DONE_CHAR
    crit_char = "!" if use_ascii else _CRIT_CHAR
    milestone_char = "*" if use_ascii else _MILESTONE_CHAR
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    axis_fmt = diagram.axis_format or _DEFAULT_AXIS_FORMAT

    # Collect all tasks and the label width
    all_tasks: list[tuple[str, list[tuple[str, datetime | None, datetime | None, str]]]] = []
    max_label_width = 0

    for section in diagram.sections:
        section_tasks: list[tuple[str, datetime | None, datetime | None, str]] = []
        for task in section.tasks:
            # Determine bar style
            if task.is_milestone:
                style = "milestone"
            elif task.is_done:
                style = "done"
            elif task.is_active:
                style = "active"
            elif task.is_crit:
                style = "crit"
            else:
                style = "normal"

            section_tasks.append((task.title, task.start, task.end, style))
            max_label_width = max(max_label_width, display_width(task.title))

        all_tasks.append((section.title, section_tasks))
        max_label_width = max(max_label_width, display_width(section.title) + 2)

    time_range = diagram.time_range()
    if time_range is None:
        return Canvas(1, 1)
    min_date, max_date = time_range

    # A chart whose tasks all share one instant still spans a day
    if max_date <= min_date:
        max_date = min_date + timedelta(days=1)

    # Layout: labels start at column 3 and need a blank column before the axis
    margin_l = max_label_width + 4
    chart_w = width - margin_l - 1
    if chart_w < 10:
        chart_w = 10
    scale = _Scale(min_date, max_date, margin_l + 1, chart_w - 1)

    # Compute rows
    title_rows = 2 if diagram.title else 0
    task_rows = 0
    for section_title, tasks in all_tasks:
        if section_title:
            task_rows += 1  # section header
        task_rows += len(tasks)

    axis_rows = 2  # axis line + date labels
    total_h = title_rows + task_rows + axis_rows + 1
    total_w = margin_l + chart_w + 1

    canvas = Canvas(total_w + 1, total_h + 1)

    # Title
    if diagram.title:
        tx = margin_l + (chart_w - display_width(diagram.title)) // 2
        canvas.put_text(0, max(0, tx), diagram.title, style="label")

    # Draw tasks
    row = title_rows
    section_idx = 0
    for section_title, tasks in all_tasks:
        if section_title:
            canvas.put_text(row, 1, section_title, style=f"sectionfg:{section_idx}")
            row += 1

        for title, start, end, style in tasks:
            # Task label (indented, truncated if needed)
            avail = margin_l - 4
            disp = truncate_to_width(title, avail)
            canvas.put_text(row, 3, disp, style="edge_label")

            if start and end:
                bar_start = scale.col(start)
                bar_end = max(scale.col(end), bar_start + 1)

                # Choose bar character
                if style == "milestone":
                    mid = (bar_start + bar_end) // 2
                    canvas.put(row, mid, milestone_char, merge=False,
                              style=f"section:{section_idx}")
                else:
                    ch = bar_char
                    if style == "done":
                        ch = done_char
                    elif style == "active":
                        ch = active_char
                    elif style == "crit":
                        ch = crit_char

                    task_style = f"section:{section_idx}"
                    for c in range(bar_start, bar_end):
                        if c < total_w:
                            canvas.put(row, c, ch, merge=False, style=task_style)

            row += 1
        section_idx += 1

    # Continuous y-axis line
    axis_row = row
    for r in range(title_rows, axis_row):
        canvas.put(r, margin_l, vt, merge=False, style="edge")

    # X-axis
    canvas.put(axis_row, margin_l, "+" if use_ascii else "└", merge=False, style="edge")
    for c in range(margin_l + 1, margin_l + chart_w):
        canvas.put(axis_row, c, hz, merge=False, style="edge")

    # Vertical markers with date labels at top
    marker_vt = "|" if use_ascii else "┊"
    for marker_date in diagram.vertical_markers:
        if scale.covers(marker_date):
            col = scale.col(marker_date)
            # Date label above the chart
            label = format_time(marker_date, axis_fmt)
            label_x = col - display_width(label) // 2
            label_row = title_rows - 1 if title_rows > 0 else 0
            canvas.put_text(label_row, max(margin_l + 1, label_x), label, style="edge_label")
            # Vertical line
            for r in range(title_rows, axis_row):
                existing = canvas.get(r, col)
                if existing == " " or existing == hz:
                    canvas.put(r, col, marker_vt, merge=False, style="edge_label")

    # Today marker
    if diagram.today_marker:
        now = datetime.now()
        if scale.covers(now):
            today_vt = "|" if use_ascii else "▎"
            col = scale.col(now)
            for r in range(title_rows, axis_row):
                existing = canvas.get(r, col)
                if existing == " ":
                    canvas.put(r, col, today_vt, merge=False, style="arrow")

    # Ticks and their labels on the x-axis
    ticks = None
    if diagram.tick_interval is not None:
        ticks = _interval_ticks(scale, diagram.tick_interval, axis_fmt)
    if ticks is None:
        ticks = _default_ticks(scale, chart_w, axis_fmt)
    label_end = -1
    for col, label in ticks:
        canvas.put(axis_row, col, "+" if use_ascii else "┬", merge=False, style="edge")
        label_w = display_width(label)
        label_x = min(max(0, col - label_w // 2), total_w + 1 - label_w)
        if label_x > label_end:
            canvas.put_text(axis_row + 1, label_x, label, style="edge_label")
            label_end = label_x + label_w

    return canvas
