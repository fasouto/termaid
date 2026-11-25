"""Renderer for quadrant chart diagrams.

Renders a 2x2 grid with labeled quadrants and data points plotted
at their (x, y) positions using marker characters.
"""
from __future__ import annotations

from ..model.quadrant import QuadrantChart
from ..utils import display_width, iter_cells, wrap_display_text
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
        pad = (_MARGIN_L + _CHART_W - display_width(diagram.title)) // 2
        lines.append(" " * max(0, pad) + diagram.title)
        lines.append("")
    # The y-axis runs up the chart, so its label heads the grid.
    if diagram.y_label:
        lines.append(" " * _MARGIN_L + ("^ " if use_ascii else "↑ ") + diagram.y_label)

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

    # Plot points: every marker first, so no label covers one.
    spots: list[tuple[int, int]] = []
    for point in diagram.points:
        px = int(point.x * (_CHART_W - 1))
        py = int((1 - point.y) * (_CHART_H - 1))  # y is inverted (0=bottom)
        px = max(0, min(_CHART_W - 1, px))
        py = max(0, min(_CHART_H - 1, py))
        grid[py][px] = marker
        spots.append((px, py))
    free = (" ", hz, vt, cross)
    for point, (px, py) in zip(diagram.points, spots):
        label = " " + point.label  # the space keeps the label off its marker
        width = display_width(label)
        # Right of the marker, then left of it, then centred on the row
        # above or below; the first that covers nothing wins.
        tries = [(py, px + 1), (py, px - width)]
        tries += [(row, max(0, min(_CHART_W - width, px - width // 2))) for row in (py - 1, py + 1)]
        fitting = [(row, col) for row, col in tries if 0 <= row < _CHART_H and 0 <= col <= _CHART_W - width]
        clear = [spot for spot in fitting if all(cell in free for cell in grid[spot[0]][spot[1]:spot[1] + width])]
        if clear or fitting:
            row, col = (clear or fitting)[0]
            _write_cells(grid[row], col, label)

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
        x_pad = _MARGIN_L + (_CHART_W - display_width(diagram.x_label)) // 2
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
    """Place a label centered at (cx, cy) in the grid, wrapped to stay inside its quadrant."""
    rows = wrap_display_text(label, _CHART_W // 2 - 2) if label else []
    top = cy - (len(rows) - 1) // 2
    for i, text in enumerate(rows):
        if 0 <= top + i < len(grid):
            _write_cells(grid[top + i], cx - display_width(text) // 2, text)


def _write_cells(row: list[str], start: int, text: str) -> None:
    """Write *text* into *row* from column *start*, one cluster per cell;
    a wide cluster leaves an empty shadow cell, as on the canvas."""
    col = start
    for cell, width in iter_cells(text):
        for offset, value in enumerate((cell, "")[:width]):
            if 0 <= col + offset < len(row):
                row[col + offset] = value
        col += width
