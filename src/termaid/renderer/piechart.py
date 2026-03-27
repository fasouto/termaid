"""Renderer for pie chart diagrams as horizontal bar charts.

Draws per-slice horizontal bars with right-aligned labels,
percentages, and optional raw values.
"""
from __future__ import annotations

from ..model.piechart import PieChart
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from ..utils import display_width

_FILL_CHARS = ["█", "▓", "░", "▒", "▞", "▚", "▖", "▗"]
_FILL_CHARS_ASCII = ["#", "*", "+", "~", ":", ".", "o", "="]

_BAR_WIDTH = 40
_MARGIN = 2


def render_pie_chart(
    diagram: PieChart,
    *,
    use_ascii: bool = False,
) -> Canvas:
    """Render a PieChart as a horizontal bar chart on a Canvas."""

    if not diagram.slices:
        canvas = Canvas(1, 1)
        return canvas

    total = sum(s.value for s in diagram.slices)
    fills = _FILL_CHARS_ASCII if use_ascii else _FILL_CHARS

    # Compute label column width
    max_label_len = max(display_width(s.label) for s in diagram.slices)
    label_col_w = max_label_len + _MARGIN

    # Compute suffix (percentage + optional value)
    suffixes: list[str] = []
    for s in diagram.slices:
        pct = s.value / total * 100
        if diagram.show_data:
            suffixes.append(f" {pct:5.1f}%  [{s.value:g}]")
        else:
            suffixes.append(f" {pct:5.1f}%")
    max_suffix_len = max(len(sf) for sf in suffixes)

    bar_left = label_col_w
    canvas_w = bar_left + _BAR_WIDTH + max_suffix_len + _MARGIN
    title_rows = 2 if diagram.title else 0

    bars_top = _MARGIN + title_rows
    canvas_h = bars_top + len(diagram.slices) + _MARGIN

    canvas = Canvas(canvas_w, canvas_h)

    # Title
    if diagram.title:
        title_col = max(0, (canvas_w - len(diagram.title)) // 2)
        canvas.put_text(_MARGIN, title_col, diagram.title, style="label")

    # ── Per-slice bars ────────────────────────────────────────────────────
    for i, s in enumerate(diagram.slices):
        row = bars_top + i
        pct = s.value / total * 100
        fill = fills[i % len(fills)]
        bar_len = max(1, round(s.value / total * _BAR_WIDTH))

        # Label (right-aligned)
        label_text = s.label.rjust(max_label_len)
        canvas.put_text(row, _MARGIN, label_text, style="label")

        # Bar
        if use_ascii:
            canvas.put(row, bar_left, "|", merge=False, style="edge")
        else:
            canvas.put(row, bar_left, "┃", merge=False, style="edge")
        for c in range(bar_len):
            canvas.put(row, bar_left + 1 + c, fill, merge=False, style="node")

        # Suffix
        canvas.put_text(row, bar_left + 1 + bar_len, suffixes[i], style="label")

    return canvas
