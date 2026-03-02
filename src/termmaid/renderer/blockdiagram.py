"""Renderer for block diagrams.

Renders a BlockDiagram to a Canvas using explicit grid-based layout.
"""
from __future__ import annotations

from ..graph.shapes import NodeShape
from ..model.blockdiagram import Block, BlockDiagram, BlockLink
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from .shapes import SHAPE_RENDERERS

# Layout constants
_BLOCK_PAD = 2
_MIN_BLOCK_W = 12
_MIN_BLOCK_H = 5
_COL_GAP = 4
_ROW_GAP = 2
_MARGIN = 2
_GROUP_PAD = 2  # inner margin for nested groups


def render_block_diagram(diagram: BlockDiagram, *, use_ascii: bool = False) -> Canvas:
    """Render a BlockDiagram to a Canvas."""
    cs = ASCII if use_ascii else UNICODE

    if not diagram.blocks:
        return Canvas(1, 1)

    columns = diagram.columns
    if columns <= 0:
        # Auto: total span of all blocks (single row)
        columns = sum(b.col_span for b in diagram.blocks)

    # Layout all blocks into a grid
    grid, col_count = _layout_grid(diagram.blocks, columns)

    # Compute block sizes
    block_sizes: dict[str, tuple[int, int]] = {}
    _compute_all_sizes(diagram.blocks, block_sizes, cs)

    # Compute column widths and row heights
    col_widths, row_heights = _compute_grid_dimensions(grid, col_count, block_sizes)

    # Compute block positions
    positions: dict[str, tuple[int, int]] = {}
    _compute_positions(grid, col_widths, row_heights, block_sizes, positions)

    # Canvas size
    total_w = _MARGIN * 2 + sum(col_widths) + _COL_GAP * max(0, col_count - 1)
    total_h = _MARGIN * 2 + sum(row_heights) + _ROW_GAP * max(0, len(grid) - 1)

    # Expand for links that might go outside
    total_w = max(total_w, 20)
    total_h = max(total_h, 5)

    canvas = Canvas(total_w, total_h)

    # Draw group borders (background)
    _draw_groups(canvas, diagram.blocks, positions, block_sizes, cs)

    # Draw links (middle layer)
    for link in diagram.links:
        _draw_link(canvas, link, positions, block_sizes, cs, use_ascii)

    # Draw block shapes (foreground)
    _draw_blocks(canvas, diagram.blocks, positions, block_sizes, cs)

    return canvas


def _layout_grid(
    blocks: list[Block], columns: int,
) -> tuple[list[list[tuple[Block, int, int]]], int]:
    """Place blocks into a grid, respecting col_span.

    Returns (grid_rows, effective_column_count).
    Each row is a list of (block, start_col, col_span).
    """
    grid: list[list[tuple[Block, int, int]]] = []
    row: list[tuple[Block, int, int]] = []
    col = 0

    for block in blocks:
        span = min(block.col_span, columns)
        if col + span > columns:
            # Wrap to next row
            if row:
                grid.append(row)
            row = []
            col = 0
        row.append((block, col, span))
        col += span

    if row:
        grid.append(row)

    return grid, columns


def _compute_block_size(block: Block, cs: CharSet) -> tuple[int, int]:
    """Compute (width, height) for a single block."""
    if block.is_space:
        return _MIN_BLOCK_W, _MIN_BLOCK_H

    if block.children:
        # Group: compute inner layout size
        inner_cols = block.columns if block.columns > 0 else sum(c.col_span for c in block.children)
        inner_grid, inner_col_count = _layout_grid(block.children, inner_cols)
        child_sizes: dict[str, tuple[int, int]] = {}
        _compute_all_sizes(block.children, child_sizes, cs)
        col_widths, row_heights = _compute_grid_dimensions(inner_grid, inner_col_count, child_sizes)
        inner_w = sum(col_widths) + _COL_GAP * max(0, inner_col_count - 1)
        inner_h = sum(row_heights) + _ROW_GAP * max(0, len(inner_grid) - 1)
        # Add group padding + borders (+ label row if labeled)
        w = inner_w + _GROUP_PAD * 2 + 2  # borders
        label_rows = 1 if block.label else 0
        h = inner_h + _GROUP_PAD * 2 + 2 + label_rows  # top/bottom border + label
        return max(w, _MIN_BLOCK_W), max(h, _MIN_BLOCK_H)

    label = block.label or block.id
    w = max(len(label) + _BLOCK_PAD * 2, _MIN_BLOCK_W)
    h = _MIN_BLOCK_H
    return w, h


def _compute_all_sizes(
    blocks: list[Block], sizes: dict[str, tuple[int, int]], cs: CharSet,
) -> None:
    """Compute sizes for all blocks recursively."""
    for block in blocks:
        sizes[block.id] = _compute_block_size(block, cs)
        if block.children:
            _compute_all_sizes(block.children, sizes, cs)


def _compute_grid_dimensions(
    grid: list[list[tuple[Block, int, int]]],
    col_count: int,
    sizes: dict[str, tuple[int, int]],
) -> tuple[list[int], list[int]]:
    """Compute column widths and row heights."""
    col_widths = [_MIN_BLOCK_W] * col_count
    row_heights = [_MIN_BLOCK_H] * len(grid)

    # First pass: single-span blocks set column widths
    for ri, row in enumerate(grid):
        for block, start_col, span in row:
            w, h = sizes.get(block.id, (_MIN_BLOCK_W, _MIN_BLOCK_H))
            row_heights[ri] = max(row_heights[ri], h)
            if span == 1:
                col_widths[start_col] = max(col_widths[start_col], w)

    # Second pass: spanning blocks may need to expand columns
    for ri, row in enumerate(grid):
        for block, start_col, span in row:
            if span <= 1:
                continue
            w, _ = sizes.get(block.id, (_MIN_BLOCK_W, _MIN_BLOCK_H))
            available = sum(col_widths[start_col:start_col + span]) + _COL_GAP * (span - 1)
            if w > available:
                extra = w - available
                per_col = extra // span
                remainder = extra % span
                for c in range(start_col, start_col + span):
                    col_widths[c] += per_col
                    if c - start_col < remainder:
                        col_widths[c] += 1

    return col_widths, row_heights


def _compute_positions(
    grid: list[list[tuple[Block, int, int]]],
    col_widths: list[int],
    row_heights: list[int],
    sizes: dict[str, tuple[int, int]],
    positions: dict[str, tuple[int, int]],
) -> None:
    """Compute (x, y) positions for all blocks."""
    # Precompute column x positions
    col_x = [0] * len(col_widths)
    x = _MARGIN
    for c in range(len(col_widths)):
        col_x[c] = x
        x += col_widths[c] + _COL_GAP

    # Precompute row y positions
    row_y = [0] * len(row_heights)
    y = _MARGIN
    for r in range(len(row_heights)):
        row_y[r] = y
        y += row_heights[r] + _ROW_GAP

    for ri, row in enumerate(grid):
        for block, start_col, span in row:
            bx = col_x[start_col]
            by = row_y[ri]

            bw, bh = sizes.get(block.id, (_MIN_BLOCK_W, _MIN_BLOCK_H))

            # Blocks stretch to fill their allocated grid cell(s)
            if span > 1:
                end_col = min(start_col + span - 1, len(col_widths) - 1)
                bw = col_x[end_col] + col_widths[end_col] - col_x[start_col]
            else:
                bw = col_widths[start_col]
            bh = row_heights[ri]
            # Update sizes so draw/link functions use the actual rendered size
            sizes[block.id] = (bw, bh)

            positions[block.id] = (bx, by)

            # Position children inside group
            if block.children:
                _position_children(block, bx, by, bw, bh, sizes, positions)


def _position_children(
    group: Block,
    gx: int, gy: int, gw: int, gh: int,
    sizes: dict[str, tuple[int, int]],
    positions: dict[str, tuple[int, int]],
) -> None:
    """Position children of a group block within its bounds."""
    inner_x = gx + _GROUP_PAD + 1  # after border + padding
    label_rows = 1 if group.label else 0
    inner_y = gy + _GROUP_PAD + 1 + label_rows  # after border + optional label + padding

    inner_cols = group.columns if group.columns > 0 else sum(c.col_span for c in group.children)
    inner_grid, inner_col_count = _layout_grid(group.children, inner_cols)
    col_widths, row_heights = _compute_grid_dimensions(inner_grid, inner_col_count, sizes)

    # Position children in inner grid
    child_col_x = [0] * len(col_widths)
    x = inner_x
    for c in range(len(col_widths)):
        child_col_x[c] = x
        x += col_widths[c] + _COL_GAP

    child_row_y = [0] * len(row_heights)
    y = inner_y
    for r in range(len(row_heights)):
        child_row_y[r] = y
        y += row_heights[r] + _ROW_GAP

    for ri, row in enumerate(inner_grid):
        for block, start_col, span in row:
            bx = child_col_x[start_col]
            by = child_row_y[ri]

            # Children stretch to fill their grid cell(s)
            if span > 1 and start_col + span - 1 < len(col_widths):
                end_col = start_col + span - 1
                bw = child_col_x[end_col] + col_widths[end_col] - child_col_x[start_col]
            else:
                bw = col_widths[start_col]
            bh = row_heights[ri]
            sizes[block.id] = (bw, bh)
            positions[block.id] = (bx, by)


def _draw_blocks(
    canvas: Canvas,
    blocks: list[Block],
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
    cs: CharSet,
) -> None:
    """Draw all block shapes."""
    for block in blocks:
        if block.is_space:
            continue
        if block.id not in positions:
            continue
        if block.children:
            _draw_blocks(canvas, block.children, positions, sizes, cs)
            continue

        x, y = positions[block.id]
        w, h = sizes.get(block.id, (_MIN_BLOCK_W, _MIN_BLOCK_H))

        # For spanning blocks, use the actual width from position calculation
        # Check if width was expanded
        shape_name = block.shape.upper()
        try:
            shape_enum = NodeShape[shape_name]
        except KeyError:
            shape_enum = NodeShape.RECTANGLE

        renderer = SHAPE_RENDERERS.get(shape_enum, SHAPE_RENDERERS[NodeShape.RECTANGLE])
        label = block.label or block.id
        renderer(canvas, x, y, w, h, label, cs, style="node")


def _draw_groups(
    canvas: Canvas,
    blocks: list[Block],
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
    cs: CharSet,
) -> None:
    """Draw group borders for nested block groups."""
    for block in blocks:
        if not block.children:
            continue
        if block.id not in positions:
            continue

        x, y = positions[block.id]
        w, h = sizes.get(block.id, (_MIN_BLOCK_W, _MIN_BLOCK_H))
        style = "subgraph"

        # Draw border using subgraph chars
        canvas.put(y, x, cs.sg_top_left, style=style)
        for c in range(x + 1, x + w - 1):
            canvas.put(y, c, cs.sg_horizontal, style=style)
        canvas.put(y, x + w - 1, cs.sg_top_right, style=style)

        canvas.put(y + h - 1, x, cs.sg_bottom_left, style=style)
        for c in range(x + 1, x + w - 1):
            canvas.put(y + h - 1, c, cs.sg_horizontal, style=style)
        canvas.put(y + h - 1, x + w - 1, cs.sg_bottom_right, style=style)

        for r in range(y + 1, y + h - 1):
            canvas.put(r, x, cs.sg_vertical, style=style)
            canvas.put(r, x + w - 1, cs.sg_vertical, style=style)

        # Draw group label (skip for anonymous groups)
        if block.label:
            label_col = x + (w - len(block.label)) // 2
            canvas.put_text(y + 1, label_col, block.label, style="label")

        # Recurse for nested groups within children
        _draw_groups(canvas, block.children, positions, sizes, cs)


def _draw_link(
    canvas: Canvas,
    link: BlockLink,
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a link between two blocks."""
    if link.source not in positions or link.target not in positions:
        return

    sx, sy = positions[link.source]
    sw, sh = sizes.get(link.source, (_MIN_BLOCK_W, _MIN_BLOCK_H))
    tx, ty = positions[link.target]
    tw, th = sizes.get(link.target, (_MIN_BLOCK_W, _MIN_BLOCK_H))

    s_cx = sx + sw // 2
    t_cx = tx + tw // 2

    h_char = cs.line_horizontal
    v_char = cs.line_vertical
    style = "edge"

    # Determine connection type based on overlap, not just center distance.
    # If blocks overlap horizontally, use vertical routing.
    # If blocks overlap vertically, use horizontal routing.
    s_right, t_right = sx + sw, tx + tw
    h_overlap = min(s_right, t_right) - max(sx, tx)
    s_bottom, t_bottom = sy + sh, ty + th
    v_overlap = min(s_bottom, t_bottom) - max(sy, ty)

    use_vertical = h_overlap > 0 or (v_overlap <= 0 and abs(t_cx - s_cx) <= abs((ty + th // 2) - (sy + sh // 2)))

    if not use_vertical:
        # Horizontal: exit/enter from sides
        dx = t_cx - s_cx
        if dx > 0:
            r1, c1 = sy + sh // 2, sx + sw
            r2, c2 = ty + th // 2, tx - 1
            arrow = cs.arrow_right
        else:
            r1, c1 = sy + sh // 2, sx - 1
            r2, c2 = ty + th // 2, tx + tw
            arrow = cs.arrow_left

        _draw_routed_line(canvas, r1, c1, r2, c2, h_char, v_char, use_ascii, style)
        canvas.put(r2, c2, arrow, merge=False, style=style)
    else:
        # Vertical: exit/enter from top/bottom
        dy = (ty + th // 2) - (sy + sh // 2)
        # Pick exit x: clamp source center to target's x range for cleaner routing
        exit_col = s_cx
        enter_col = max(tx, min(t_cx, s_right - 1))
        # But if source is inside/overlapping target, just use source center
        if h_overlap > 0:
            enter_col = exit_col

        if dy > 0:
            r1, c1 = sy + sh, exit_col
            r2, c2 = ty - 1, enter_col
        else:
            r1, c1 = sy - 1, exit_col
            r2, c2 = ty + th, enter_col

        if c1 == c2:
            # Straight vertical
            for r in range(min(r1, r2), max(r1, r2) + 1):
                canvas.put(r, c1, v_char, style=style)
        else:
            # L-route: vertical to bend row, then horizontal to target x
            bend_row = r2
            for r in range(min(r1, bend_row), max(r1, bend_row) + 1):
                canvas.put(r, c1, v_char, style=style)
            for c in range(min(c1, c2), max(c1, c2) + 1):
                canvas.put(bend_row, c, h_char, style=style)
            if not use_ascii:
                if r1 < bend_row:
                    corner = "┘" if c2 < c1 else "└"
                else:
                    corner = "┐" if c2 < c1 else "┌"
                canvas.put(bend_row, c1, corner, style=style)

        arrow = cs.arrow_down if dy > 0 else cs.arrow_up
        canvas.put(r2, c2, arrow, merge=False, style=style)

    # Draw label
    if link.label:
        mid_r = (r1 + r2) // 2
        mid_c = (c1 + c2) // 2
        label_col = mid_c - len(link.label) // 2
        canvas.put_text(mid_r, label_col, link.label, style="edge_label")


def _draw_routed_line(
    canvas: Canvas,
    r1: int, c1: int, r2: int, c2: int,
    h_char: str, v_char: str, use_ascii: bool,
    style: str = "edge",
) -> None:
    """Draw a routed line from (r1,c1) to (r2,c2)."""
    if c1 == c2:
        for r in range(min(r1, r2), max(r1, r2) + 1):
            canvas.put(r, c1, v_char, style=style)
    elif r1 == r2:
        for c in range(min(c1, c2), max(c1, c2) + 1):
            canvas.put(r1, c, h_char, style=style)
    else:
        mid_row = (r1 + r2) // 2
        for r in range(min(r1, mid_row), max(r1, mid_row) + 1):
            canvas.put(r, c1, v_char, style=style)
        for c in range(min(c1, c2), max(c1, c2) + 1):
            canvas.put(mid_row, c, h_char, style=style)
        for r in range(min(mid_row, r2), max(mid_row, r2) + 1):
            canvas.put(r, c2, v_char, style=style)
        if not use_ascii:
            if r1 < mid_row:
                corner1 = "┘" if c2 < c1 else "└"
            else:
                corner1 = "┐" if c2 < c1 else "┌"
            canvas.put(mid_row, c1, corner1, style=style)
            if r2 > mid_row:
                corner2 = "┌" if c2 < c1 else "┐"
            else:
                corner2 = "└" if c2 < c1 else "┘"
            canvas.put(mid_row, c2, corner2, style=style)
