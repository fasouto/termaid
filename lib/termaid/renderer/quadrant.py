"""Renderer for quadrant chart diagrams.

Renders a 2x2 grid with labeled quadrants and data points plotted
at their (x, y) positions using marker characters.
"""
from __future__ import annotations

from ..model.quadrant import QuadrantChart
from ..utils import display_width
from .canvas import Canvas


_CHART_W = 60  # chart area width
_CHART_H = 20  # chart area height
_MARGIN_L = 2  # left margin for y-axis label
_MARGIN_B = 2  # bottom margin for x-axis label


def render_quadrant(
    diagram: QuadrantChart,
    *,
    use_ascii: bool = False,
) -> Canvas:
    """Render a QuadrantChart model to a Canvas."""
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    cross = "+" if use_ascii else "┼"
    marker = "*" if use_ascii else "●"
    corner = "+" if use_ascii else "└"

    lines: list[str] = []

    # Title
    if diagram.title:
        pad = (_MARGIN_L + _CHART_W - len(diagram.title)) // 2
        lines.append(" " * max(0, pad) + diagram.title)
        lines.append("")

    # Build the chart grid
    # Quadrant labels centered in their quadrant
    q2_label = diagram.quadrant_2  # top-left
    q1_label = diagram.quadrant_1  # top-right
    q3_label = diagram.quadrant_3  # bottom-left
    q4_label = diagram.quadrant_4  # bottom-right

    half_w = _CHART_W // 2
    half_h = _CHART_H // 2

    # Create empty grid
    grid: list[list[str]] = [[" " for _ in range(_CHART_W)] for _ in range(_CHART_H)]

    # Place quadrant labels (centered in each quadrant)
    _place_label(grid, q2_label, half_w // 2, half_h // 2)     # top-left
    _place_label(grid, q1_label, half_w + half_w // 2, half_h // 2)  # top-right
    _place_label(grid, q3_label, half_w // 2, half_h + half_h // 2)  # bottom-left
    _place_label(grid, q4_label, half_w + half_w // 2, half_h + half_h // 2)  # bottom-right

    # Draw axes (center lines)
    for c in range(_CHART_W):
        grid[half_h][c] = hz
    for r in range(_CHART_H):
        grid[r][half_w] = vt
    grid[half_h][half_w] = cross

    # Plot points
    for point in diagram.points:
        px = int(point.x * (_CHART_W - 1))
        py = int((1 - point.y) * (_CHART_H - 1))  # y is inverted (0=bottom)
        px = max(0, min(_CHART_W - 1, px))
        py = max(0, min(_CHART_H - 1, py))
        grid[py][px] = marker
        # Place label to the right of the marker (with 1 char gap)
        label = " " + point.label
        start = px + 1
        if start + display_width(label) > _CHART_W:
            # Doesn't fit on right, try left
            start = px - display_width(label)
        if start >= 0:
            for i, ch in enumerate(label):
                if 0 <= start + i < _CHART_W:
                    grid[py][start + i] = ch

    # Build a style grid matching the char grid
    style_grid: list[list[str]] = [["default" for _ in range(_CHART_W)] for _ in range(_CHART_H)]
    for r in range(_CHART_H):
        for c in range(_CHART_W):
            if r < half_h and c < half_w:
                style_grid[r][c] = "section:1"   # Q2 top-left
            elif r < half_h and c >= half_w:
                style_grid[r][c] = "section:0"   # Q1 top-right
            elif r >= half_h and c < half_w:
                style_grid[r][c] = "section:2"   # Q3 bottom-left
            else:
                style_grid[r][c] = "section:3"   # Q4 bottom-right
    # Axes get edge style
    for c in range(_CHART_W):
        style_grid[half_h][c] = "edge"
    for r in range(_CHART_H):
        style_grid[r][half_w] = "edge"

    # Render grid with left margin
    title_lines = len(lines)  # lines added before the grid (title)

    # X-axis label
    x_label_line = ""
    if diagram.x_label:
        x_pad = _MARGIN_L + (_CHART_W - len(diagram.x_label)) // 2
        x_label_line = " " * max(0, x_pad) + diagram.x_label

    # Compute canvas size
    total_h = title_lines + _CHART_H + (2 if x_label_line else 0)
    width = _MARGIN_L + _CHART_W + 1
    canvas = Canvas(width, total_h)

    # Write title lines
    for r, line in enumerate(lines):
        canvas.put_text(r, 0, line, style="label")

    # Write ALL grid cells (including spaces) so backgrounds fill
    # the entire quadrant region. For non-space chars, use put().
    # For spaces, write the style directly since put() skips them.
    for r in range(_CHART_H):
        row_y = title_lines + r
        for c in range(_CHART_W):
            col_x = _MARGIN_L + c
            ch = grid[r][c]
            style = style_grid[r][c]
            if ch != " ":
                canvas.put(row_y, col_x, ch, merge=False, style=style)
            else:
                canvas._style_grid[row_y][col_x] = style

    # Write x-axis label
    if x_label_line:
        canvas.put_text(title_lines + _CHART_H + 1, 0, x_label_line, style="edge_label")

    return canvas


def _place_label(grid: list[list[str]], label: str, cx: int, cy: int) -> None:
    """Place a label centered at (cx, cy) in the grid."""
    start_x = cx - display_width(label) // 2
    w = len(grid[0]) if grid else 0
    for i, ch in enumerate(label):
        x = start_x + i
        if 0 <= x < w and 0 <= cy < len(grid):
            grid[cy][x] = ch
