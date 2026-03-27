"""Renderer for XY chart diagrams.

Renders bar charts and line charts on labeled axes.
Supports vertical (default) and horizontal orientations.
"""
from __future__ import annotations

from ..model.xychart import XYChart
from ..utils import display_width
from .canvas import Canvas

_CHART_H = 12     # chart area height (rows for data) in vertical mode
_CHART_W = 50     # chart area width in horizontal mode
_BAR_CHAR = "█"
_BAR_HALF = "▄"
_BAR_HALF_H = "▌"  # half block for horizontal bars
_LINE_MARKER = "●"
_BAR_WIDTH = 4    # width of each bar in vertical mode
_BAR_GAP = 2      # gap between bars
_MARGIN_L = 8     # left margin for y-axis labels


def render_xychart(
    diagram: XYChart,
    *,
    use_ascii: bool = False,
    rounded: bool = True,
) -> Canvas:
    """Render an XYChart model to a Canvas."""
    if not diagram.datasets:
        return Canvas(1, 1)

    # Horizontal mode only applies to bar-only charts.
    # Line charts always render vertically since they need a
    # continuous axis to show trends.
    has_line = any(ds.chart_type == "line" for ds in diagram.datasets)
    if diagram.horizontal and not has_line:
        return _render_horizontal(diagram, use_ascii=use_ascii)
    return _render_vertical(diagram, use_ascii=use_ascii, rounded=rounded)


# ---------------------------------------------------------------------------
# Vertical chart (default)
# ---------------------------------------------------------------------------

def _render_vertical(diagram: XYChart, use_ascii: bool = False, rounded: bool = True) -> Canvas:
    bar_char = "#" if use_ascii else _BAR_CHAR
    bar_half = "=" if use_ascii else _BAR_HALF
    marker = "*" if use_ascii else _LINE_MARKER
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    corner = "+" if use_ascii else "└"
    tick = "+" if use_ascii else "┬"
    left_tick = "+" if use_ascii else "┤"

    # Compute value range
    all_values: list[float] = []
    for ds in diagram.datasets:
        all_values.extend(ds.values)
    if not all_values:
        return Canvas(1, 1)

    max_val = max(all_values)
    min_val = min(0, min(all_values))
    if diagram.y_range:
        min_val, max_val = diagram.y_range
    val_range = max_val - min_val
    if val_range == 0:
        val_range = 1

    n_points = max(len(ds.values) for ds in diagram.datasets)

    # Categories
    categories = list(diagram.x_categories[:n_points])
    if diagram.x_range and not categories:
        lo, hi = diagram.x_range
        step = (hi - lo) / max(n_points - 1, 1)
        categories = [_format_val(lo + i * step) for i in range(n_points)]
    while len(categories) < n_points:
        categories.append(str(len(categories) + 1))

    cat_width = max(display_width(c) for c in categories) if categories else 2
    col_width = max(_BAR_WIDTH, cat_width + 1)

    chart_w = n_points * (col_width + _BAR_GAP) - _BAR_GAP
    total_w = _MARGIN_L + 1 + chart_w + 2

    title_lines = 2 if diagram.title else 0
    total_h = _CHART_H + 4

    canvas = Canvas(total_w + 1, total_h + title_lines + 1)
    row_offset = title_lines

    # Title
    if diagram.title:
        title_x = _MARGIN_L + (chart_w - display_width(diagram.title)) // 2
        canvas.put_text(0, max(0, title_x), diagram.title, style="label")

    # Y-axis labels
    n_ticks = 5
    for i in range(n_ticks + 1):
        val = min_val + val_range * (n_ticks - i) / n_ticks
        label = _format_val(val)
        label_x = _MARGIN_L - display_width(label) - 1
        row = row_offset + i * _CHART_H // n_ticks
        canvas.put_text(row, max(0, label_x), label, style="edge_label")
        canvas.put(row, _MARGIN_L, left_tick, merge=False, style="edge")

    # Y-axis line
    for r in range(row_offset, row_offset + _CHART_H + 1):
        canvas.put(r, _MARGIN_L, vt, merge=False, style="edge")

    # X-axis line
    axis_row = row_offset + _CHART_H
    canvas.put(axis_row, _MARGIN_L, corner, merge=False, style="edge")
    for c in range(_MARGIN_L + 1, _MARGIN_L + 1 + chart_w):
        canvas.put(axis_row, c, hz, merge=False, style="edge")

    # Draw datasets
    for ds in diagram.datasets:
        for i, val in enumerate(ds.values):
            if i >= n_points:
                break
            col_x = _MARGIN_L + 1 + i * (col_width + _BAR_GAP)
            bar_h = int((val - min_val) / val_range * _CHART_H)

            if ds.chart_type == "bar":
                for r in range(bar_h):
                    row = row_offset + _CHART_H - 1 - r
                    for c in range(col_width):
                        canvas.put(row, col_x + c, bar_char, merge=False,
                                  style=f"section:{i % 8}")
                frac = (val - min_val) / val_range * _CHART_H - bar_h
                if frac > 0.3 and bar_h < _CHART_H:
                    row = row_offset + _CHART_H - 1 - bar_h
                    for c in range(col_width):
                        canvas.put(row, col_x + c, bar_half, merge=False,
                                  style=f"section:{i % 8}")
            else:
                row = row_offset + _CHART_H - 1 - max(0, bar_h - 1)
                mid_x = col_x + col_width // 2
                # Place a line segment at the data point position
                line_ch = "-" if use_ascii else "─"
                canvas.put(row, mid_x, line_ch, merge=False, style="edge")

                if i > 0:
                    prev_val = ds.values[i - 1]
                    prev_h = int((prev_val - min_val) / val_range * _CHART_H)
                    prev_row = row_offset + _CHART_H - 1 - max(0, prev_h - 1)
                    prev_x = _MARGIN_L + 1 + (i - 1) * (col_width + _BAR_GAP) + col_width // 2
                    _draw_line_v(canvas, prev_x, prev_row, mid_x, row, use_ascii, rounded)

    # X-axis ticks and labels
    for i, cat in enumerate(categories):
        col_x = _MARGIN_L + 1 + i * (col_width + _BAR_GAP) + col_width // 2
        canvas.put(axis_row, col_x, tick, merge=False, style="edge")
        label_x = col_x - display_width(cat) // 2
        canvas.put_text(axis_row + 1, max(0, label_x), cat, style="edge_label")

    if diagram.x_label:
        lx = _MARGIN_L + 1 + (chart_w - display_width(diagram.x_label)) // 2
        canvas.put_text(axis_row + 2, max(0, lx), diagram.x_label, style="edge_label")

    return canvas


# ---------------------------------------------------------------------------
# Horizontal chart
# ---------------------------------------------------------------------------

def _render_horizontal(diagram: XYChart, use_ascii: bool = False) -> Canvas:
    bar_char = "#" if use_ascii else _BAR_CHAR
    bar_half = "|" if use_ascii else _BAR_HALF_H
    marker = "*" if use_ascii else _LINE_MARKER
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    corner = "+" if use_ascii else "└"
    tick = "+" if use_ascii else "├"
    bottom_tick = "+" if use_ascii else "┬"

    all_values: list[float] = []
    for ds in diagram.datasets:
        all_values.extend(ds.values)
    if not all_values:
        return Canvas(1, 1)

    max_val = max(all_values)
    min_val = min(0, min(all_values))
    if diagram.y_range:
        min_val, max_val = diagram.y_range
    val_range = max_val - min_val
    if val_range == 0:
        val_range = 1

    n_points = max(len(ds.values) for ds in diagram.datasets)

    # Categories (displayed on the y-axis in horizontal mode)
    categories = list(diagram.x_categories[:n_points])
    if diagram.x_range and not categories:
        lo, hi = diagram.x_range
        step = (hi - lo) / max(n_points - 1, 1)
        categories = [_format_val(lo + i * step) for i in range(n_points)]
    while len(categories) < n_points:
        categories.append(str(len(categories) + 1))

    cat_width = max(display_width(c) for c in categories) if categories else 2
    margin_l = cat_width + 2  # space for category labels + padding

    bar_height = 1  # each bar is 1 row tall
    row_gap = 1     # gap between rows
    chart_h = n_points * (bar_height + row_gap) - row_gap
    chart_w = _CHART_W

    title_lines = 2 if diagram.title else 0
    total_h = title_lines + chart_h + 3  # chart + axis + value labels
    total_w = margin_l + 1 + chart_w + 2

    canvas = Canvas(total_w + 1, total_h + 1)
    row_offset = title_lines

    # Title
    if diagram.title:
        title_x = margin_l + (chart_w - display_width(diagram.title)) // 2
        canvas.put_text(0, max(0, title_x), diagram.title, style="label")

    # Y-axis (categories on the left)
    for r in range(row_offset, row_offset + chart_h + 1):
        canvas.put(r, margin_l, vt, merge=False, style="edge")

    # X-axis (values on the bottom)
    axis_row = row_offset + chart_h
    canvas.put(axis_row, margin_l, corner, merge=False, style="edge")
    for c in range(margin_l + 1, margin_l + 1 + chart_w):
        canvas.put(axis_row, c, hz, merge=False, style="edge")

    # X-axis value labels (bottom)
    n_ticks = 5
    for i in range(n_ticks + 1):
        val = min_val + val_range * i / n_ticks
        label = _format_val(val)
        col = margin_l + 1 + int(i / n_ticks * (chart_w - 1))
        canvas.put(axis_row, col, bottom_tick, merge=False, style="edge")
        label_x = col - display_width(label) // 2
        canvas.put_text(axis_row + 1, max(0, label_x), label, style="edge_label")

    if diagram.x_label:
        lx = margin_l + 1 + (chart_w - display_width(diagram.x_label)) // 2
        canvas.put_text(axis_row + 2, max(0, lx), diagram.x_label, style="edge_label")

    # Draw datasets
    for ds in diagram.datasets:
        for i, val in enumerate(ds.values):
            if i >= n_points:
                break
            row = row_offset + i * (bar_height + row_gap)
            bar_w = int((val - min_val) / val_range * chart_w)

            # Category label
            cat = categories[i] if i < len(categories) else ""
            label_x = margin_l - display_width(cat) - 1
            canvas.put_text(row, max(0, label_x), cat, style="edge_label")
            # Don't draw tick on category rows; the axis │ is enough

            for c in range(bar_w):
                canvas.put(row, margin_l + 1 + c, bar_char, merge=False,
                          style=f"section:{i % 8}")

    return canvas


# ---------------------------------------------------------------------------
# Line drawing helpers
# ---------------------------------------------------------------------------

def _draw_line_v(canvas: Canvas, x1: int, y1: int, x2: int, y2: int, use_ascii: bool, rounded: bool = True) -> None:
    """Draw a connecting line between two markers (vertical chart)."""
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    if use_ascii:
        tl, tr, bl, br = "+", "+", "+", "+"
    elif rounded:
        tl, tr, bl, br = "╭", "╮", "╰", "╯"
    else:
        tl, tr, bl, br = "┌", "┐", "└", "┘"

    if y1 == y2:
        for x in range(x1 + 1, x2):
            canvas.put(y1, x, hz, merge=False, style="edge")
    else:
        mid_x = (x1 + x2) // 2
        going_up = y2 < y1

        for x in range(x1 + 1, mid_x):
            canvas.put(y1, x, hz, merge=False, style="edge")

        if going_up:
            canvas.put(y1, mid_x, br, merge=False, style="edge")
        else:
            canvas.put(y1, mid_x, tr, merge=False, style="edge")

        r_min, r_max = min(y1, y2), max(y1, y2)
        for r in range(r_min + 1, r_max):
            canvas.put(r, mid_x, vt, merge=False, style="edge")

        if going_up:
            canvas.put(y2, mid_x, tl, merge=False, style="edge")
        else:
            canvas.put(y2, mid_x, bl, merge=False, style="edge")

        for x in range(mid_x + 1, x2):
            canvas.put(y2, x, hz, merge=False, style="edge")


def _draw_line_h(canvas: Canvas, x1: int, y1: int, x2: int, y2: int, use_ascii: bool) -> None:
    """Draw a connecting line between two markers (horizontal chart)."""
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    if use_ascii:
        tl, tr, bl, br = "+", "+", "+", "+"
    else:
        tl, tr, bl, br = "╭", "╮", "╰", "╯"

    if x1 == x2:
        for r in range(y1 + 1, y2):
            canvas.put(r, x1, vt, merge=False, style="edge")
    else:
        mid_y = (y1 + y2) // 2
        going_right = x2 > x1

        for r in range(y1 + 1, mid_y):
            canvas.put(r, x1, vt, merge=False, style="edge")

        if going_right:
            canvas.put(mid_y, x1, bl, merge=False, style="edge")
        else:
            canvas.put(mid_y, x1, br, merge=False, style="edge")

        c_min, c_max = min(x1, x2), max(x1, x2)
        for c in range(c_min + 1, c_max):
            canvas.put(mid_y, c, hz, merge=False, style="edge")

        if going_right:
            canvas.put(mid_y, x2, tr, merge=False, style="edge")
        else:
            canvas.put(mid_y, x2, tl, merge=False, style="edge")

        for r in range(mid_y + 1, y2):
            canvas.put(r, x2, vt, merge=False, style="edge")


def _format_val(val: float) -> str:
    if val == int(val):
        return str(int(val))
    return f"{val:.1f}"
