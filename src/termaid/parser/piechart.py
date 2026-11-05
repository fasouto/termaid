"""Parser for Mermaid pie chart diagrams.

Syntax:
    pie [showData] [title <text>]
        [title <text>]
        "<label>" : <value>
        ...
"""
from __future__ import annotations

import re

from ..model.piechart import PieChart, PieSlice

_SLICE_RE = re.compile(r'^\s*"([^"]+)"\s*:\s*([0-9]+(?:\.[0-9]*)?)$')


def parse_pie_chart(text: str) -> PieChart:
    """Parse a mermaid pie chart definition."""
    lines = text.strip().splitlines()
    chart = PieChart()

    if not lines:
        return chart

    header = lines[0].strip()[len("pie"):].strip()
    if header.startswith("showData"):
        chart.show_data = True
        header = header[len("showData"):]

    for line in [header, *lines[1:]]:
        stripped = line.strip()
        if not stripped:
            continue

        # Strip comments
        comment_idx = stripped.find("%%")
        if comment_idx >= 0:
            stripped = stripped[:comment_idx].strip()
            if not stripped:
                continue

        # Title
        if stripped.lower().startswith("title "):
            chart.title = stripped[6:].strip()
            continue

        # Slice: "Label" : value
        m = _SLICE_RE.match(stripped)
        if m:
            label = m.group(1)
            value = float(m.group(2))
            if value <= 0:
                chart.warnings.append(f"Pie slice value must be positive: {label} = {value}")
                continue
            chart.slices.append(PieSlice(label=label, value=value))
            continue

        # Unrecognized line
        if stripped:
            chart.warnings.append(f"Unrecognized line: {stripped}")

    return chart
