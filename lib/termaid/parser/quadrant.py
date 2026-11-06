"""Parser for Mermaid quadrant chart diagrams.

Syntax:
    quadrantChart
        title Effort vs Impact
        x-axis Low Effort --> High Effort
        y-axis Low Impact --> High Impact
        quadrant-1 Do First
        quadrant-2 Plan
        quadrant-3 Delegate
        quadrant-4 Eliminate
        Task A: [0.8, 0.9]
        Task B: [0.2, 0.3]
"""
from __future__ import annotations

import re

from ..model.quadrant import QuadrantChart, QuadrantPoint


def parse_quadrant(text: str) -> QuadrantChart:
    """Parse a mermaid quadrant chart definition."""
    lines = text.strip().splitlines()
    qc = QuadrantChart()

    if not lines:
        return qc

    for line in lines[1:]:  # skip "quadrantChart" header
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()

        if lower.startswith("title "):
            qc.title = stripped[6:].strip()
        elif lower.startswith("x-axis "):
            # "x-axis Low --> High" or just "x-axis Label"
            label = stripped[7:].strip()
            qc.x_label = label.replace(" --> ", " -> ")
        elif lower.startswith("y-axis "):
            label = stripped[7:].strip()
            qc.y_label = label.replace(" --> ", " -> ")
        elif lower.startswith("quadrant-1 "):
            qc.quadrant_1 = stripped[11:].strip()
        elif lower.startswith("quadrant-2 "):
            qc.quadrant_2 = stripped[11:].strip()
        elif lower.startswith("quadrant-3 "):
            qc.quadrant_3 = stripped[11:].strip()
        elif lower.startswith("quadrant-4 "):
            qc.quadrant_4 = stripped[11:].strip()
        else:
            # Try to parse as a point: "Label: [x, y]"
            m = re.match(r'^(.+?):\s*\[\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\]', stripped)
            if m:
                label = m.group(1).strip()
                x = float(m.group(2))
                y = float(m.group(3))
                qc.points.append(QuadrantPoint(label=label, x=x, y=y))

    return qc
