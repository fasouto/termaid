"""Coordinate conversion for the layout engine.

Converts grid positions to drawing (character) coordinates and adjusts
for subgraph bounds that extend into negative space.
"""
from __future__ import annotations

from .grid import GridLayout


def compute_draw_coords(layout: GridLayout) -> None:
    """Convert grid positions to drawing coordinates."""
    for placement in layout.placements.values():
        gc = placement.grid
        # Top-left of the 3x3 block
        x, y = layout.grid_to_draw(gc.col - 1, gc.row - 1)
        w = sum(layout.col_widths.get(gc.col + dc, 1) for dc in range(-1, 2))
        h = sum(layout.row_heights.get(gc.row + dr, 1) for dr in range(-1, 2))
        placement.draw_x = x
        placement.draw_y = y
        placement.draw_width = w
        placement.draw_height = h


def adjust_for_negative_bounds(layout: GridLayout) -> None:
    """Shift all coordinates if subgraph bounds extend into negative space."""
    if not layout.subgraph_bounds:
        return

    min_x = 0
    min_y = 0
    for sb in layout.subgraph_bounds:
        min_x = min(min_x, sb.x)
        min_y = min(min_y, sb.y)

    if min_x >= 0 and min_y >= 0:
        return

    dx = -min_x + 1 if min_x < 0 else 0
    dy = -min_y + 1 if min_y < 0 else 0

    for p in layout.placements.values():
        p.draw_x += dx
        p.draw_y += dy

    for sb in layout.subgraph_bounds:
        sb.x += dx
        sb.y += dy

    layout.offset_x += dx
    layout.offset_y += dy
