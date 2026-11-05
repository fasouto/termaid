"""Renderer for pie chart diagrams as horizontal bar charts.

Draws per-slice horizontal bars with right-aligned labels,
percentages, and optional raw values.
"""
from __future__ import annotations

from ..model.piechart import PieChart
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from ..utils import display_width

_FILL_CHARS = ["█", "░", "▒", "▚", "▞", "▄", "▀", "▌"]
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
    # One cell per slice at least, so a chart with more slices than cells
    # gets a longer stacked bar instead of losing slices.
    stacked_w = max(_BAR_WIDTH, len(diagram.slices))
    canvas_w = bar_left + _BAR_WIDTH + max_suffix_len + _MARGIN
    canvas_w = max(canvas_w, bar_left + 1 + stacked_w + _MARGIN)
    if diagram.title:
        canvas_w = max(canvas_w, display_width(diagram.title) + 2 * _MARGIN)
    title_rows = 2 if diagram.title else 0

    # Layout: title, stacked bar (3 rows), blank, per-slice bars
    stacked_top = _MARGIN + title_rows
    bars_top = stacked_top + 4  # stacked bar + labels row + blank
    canvas_h = bars_top + len(diagram.slices) + _MARGIN

    canvas = Canvas(canvas_w, canvas_h)

    # Title
    if diagram.title:
        title_col = max(0, (canvas_w - display_width(diagram.title)) // 2)
        canvas.put_text(_MARGIN, title_col, diagram.title, style="label")

    # Stacked bar showing parts of a whole
    stacked_left = bar_left + 1
    widths = [max(1, round(s.value / total * stacked_w)) for s in diagram.slices]
    rest = stacked_w - sum(widths[:-1])
    if rest > 0:
        widths[-1] = rest
    # Rounding every slice up to a cell can overflow the bar. The widest
    # segments give up the extra cells, so no slice is squeezed out.
    while sum(widths) > stacked_w and max(widths) > 1:
        widths[widths.index(max(widths))] -= 1
    col = 0
    label_parts: list[tuple[int, int, str, str]] = []  # (start, width, named, pct)
    for i, (s, seg_w) in enumerate(zip(diagram.slices, widths)):
        fill = fills[i % len(fills)]
        for c in range(seg_w):
            canvas.put(stacked_top, stacked_left + col + c, fill, merge=False, style="node")
        pct_label = f"{s.value / total * 100:.0f}%"
        label_parts.append((col, seg_w, f"{s.label} {pct_label}", pct_label))
        col += seg_w

    # Name every slice or none. A mixed row reads as if the bare percentages
    # were unnamed slices, and the per-slice bars below already name each one.
    show_names = all(display_width(named) <= seg_w for _, seg_w, named, _ in label_parts)
    label_row = stacked_top + 1
    for start, seg_w, named, pct_label in label_parts:
        text = named if show_names else pct_label
        tw = display_width(text)
        if show_names or (seg_w >= 4 and tw <= seg_w):
            lx = stacked_left + start + (seg_w - tw) // 2
            canvas.put_text(label_row, lx, text, style="label")

    # Per-slice bars (uniform fill)
    for i, s in enumerate(diagram.slices):
        row = bars_top + i
        fill = fills[i % len(fills)]
        bar_len = max(1, round(s.value / total * _BAR_WIDTH))

        # Label (right-aligned)
        label_text = " " * (max_label_len - display_width(s.label)) + s.label
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
