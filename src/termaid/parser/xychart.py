"""Parser for Mermaid XY chart diagrams.

Syntax:
    xychart-beta [horizontal]
        title "Revenue"
        x-axis [Q1, Q2, Q3, Q4]
        x-axis "Month" [Jan, Feb, Mar]
        x-axis "Score" 0 --> 100
        y-axis "Revenue (M)"
        y-axis "Value" 0 --> 50
        bar [10, 25, 18, 32]
        line [8, 20, 15, 30]
"""
from __future__ import annotations

import math
import re

from ..model.xychart import XYChart, XYDataset

# A number that float() is guaranteed to accept (rejects e.g. "0.1.2")
_NUM = r"-?\d+(?:\.\d+)?"
# An axis: an optional title, quoted or not, then categories or a range.
_AXIS = re.compile(rf'^(.*?)\s*(?:\[(.*)\]|(?<!\S)({_NUM})\s*-->\s*({_NUM}))?\s*$')
_LIMIT = 1e300
_LIST_ITEM = re.compile(r'\s*(?:"[^"]*"|[^,]+)')


def parse_xychart(text: str) -> XYChart:
    """Parse a mermaid XY chart definition."""
    lines = text.strip().splitlines()
    chart = XYChart()

    if not lines:
        return chart

    # Parse header for orientation
    header = lines[0].strip().lower()
    if "horizontal" in header:
        chart.horizontal = True

    for line in lines[1:]:
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()

        if lower.startswith("title "):
            chart.title = _strip_quotes(stripped[6:].strip())
        elif lower.startswith("x-axis "):
            _parse_axis(stripped[7:].strip(), chart, is_x=True)
        elif lower.startswith("y-axis "):
            _parse_axis(stripped[7:].strip(), chart, is_x=False)
        elif lower.startswith("bar "):
            values = _parse_number_list(stripped[4:].strip())
            if values:
                chart.datasets.append(XYDataset(values=values, chart_type="bar"))
        elif lower.startswith("line "):
            values = _parse_number_list(stripped[5:].strip())
            if values:
                chart.datasets.append(XYDataset(values=values, chart_type="line"))

    return chart


def _parse_axis(rest: str, chart: XYChart, is_x: bool) -> None:
    """Parse axis config: an optional title, then categories or a numeric range."""
    m = _AXIS.match(rest)
    label = _strip_quotes(m.group(1))
    if is_x:
        chart.x_label = label or chart.x_label
    else:
        chart.y_label = label or chart.y_label
    if m.group(2) is not None:
        if is_x:
            items = (_strip_quotes(item.strip()) for item in _LIST_ITEM.findall(m.group(2)))
            chart.x_categories = [item for item in items if item]
    elif m.group(3) is not None:
        axis_range = (_bounded(float(m.group(3))), _bounded(float(m.group(4))))
        if is_x:
            chart.x_range = axis_range
        else:
            chart.y_range = axis_range


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _parse_number_list(text: str) -> list[float]:
    """Parse [1, 2, 3] into a list of floats."""
    m = re.match(r'\[(.+)\]', text)
    if not m:
        return []
    items = m.group(1).split(",")
    result: list[float] = []
    for item in items:
        item = item.strip().lstrip("+")
        try:
            value = float(item)
        except ValueError:
            continue
        # Mermaid reads only plain numbers, never inf or nan.
        if math.isfinite(value):
            result.append(_bounded(value))
    return result


def _bounded(value: float) -> float:
    """*value* held within ±1e300, so the chart's arithmetic cannot overflow."""
    return max(-_LIMIT, min(_LIMIT, value))
