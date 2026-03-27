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

import re

from ..model.xychart import XYChart, XYDataset


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
    """Parse axis config: title, categories, or numeric range."""
    # Try: "title" [cat1, cat2, ...]
    m = re.match(r'^"([^"]+)"\s*\[(.+)\]', rest)
    if m:
        if is_x:
            chart.x_label = m.group(1)
            chart.x_categories = [_strip_quotes(c.strip()) for c in m.group(2).split(",")]
        else:
            chart.y_label = m.group(1)
        return

    # Try: [cat1, cat2, ...]
    bracket = _parse_bracket_list(rest)
    if bracket is not None:
        if is_x:
            chart.x_categories = bracket
        return

    # Try: title min --> max  or  "title" min --> max
    m = re.match(r'^(?:"([^"]+)"|(\S+))\s+(-?[\d.]+)\s*-->\s*(-?[\d.]+)', rest)
    if m:
        label = m.group(1) or m.group(2)
        lo, hi = float(m.group(3)), float(m.group(4))
        if is_x:
            chart.x_label = label
            chart.x_range = (lo, hi)
        else:
            chart.y_label = label
            chart.y_range = (lo, hi)
        return

    # Try: min --> max (no title)
    m = re.match(r'^(-?[\d.]+)\s*-->\s*(-?[\d.]+)', rest)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if is_x:
            chart.x_range = (lo, hi)
        else:
            chart.y_range = (lo, hi)
        return

    # Just a title/label
    if is_x:
        chart.x_label = _strip_quotes(rest)
    else:
        chart.y_label = _strip_quotes(rest)


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _parse_bracket_list(text: str) -> list[str] | None:
    """Parse [item1, item2, ...] into a list of strings."""
    m = re.match(r'\[(.+)\]', text)
    if not m:
        return None
    items = m.group(1).split(",")
    return [_strip_quotes(item.strip()) for item in items if item.strip()]


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
            result.append(float(item))
        except ValueError:
            continue
    return result
