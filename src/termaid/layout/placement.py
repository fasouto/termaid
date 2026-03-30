"""Node placement and sizing for the layout engine.

Handles placing nodes on the grid, computing column widths and row
heights based on label content, and normalizing sizes within layers.
"""
from __future__ import annotations

from ..graph.model import Direction, Graph
from ..graph.shapes import NodeShape
from ..utils import display_width
from .grid import (
    STRIDE,
    MAX_LABEL_WIDTH,
    MAX_NORMALIZED_WIDTH,
    MAX_NORMALIZED_HEIGHT,
    GridCoord,
    GridLayout,
    NodePlacement,
)


def place_nodes(
    graph: Graph,
    layout: GridLayout,
    layer_order: list[list[str]],
    direction: Direction,
    gap_expansions: dict[int, int] | None = None,
) -> None:
    """Place nodes on the grid based on layer assignments.

    gap_expansions maps gap index to the number of extra grid cells to
    insert between that gap's adjacent layers, giving the pathfinder more
    room to route crossing edges without overlap.
    """
    expansions = gap_expansions or {}
    cumulative_extra = 0
    for layer_idx, nodes in enumerate(layer_order):
        if layer_idx > 0:
            cumulative_extra += expansions.get(layer_idx - 1, 0)
        for pos_idx, nid in enumerate(nodes):
            if direction.is_horizontal:
                col = layer_idx * STRIDE + 1 + cumulative_extra
                row = pos_idx * STRIDE + 1
            else:
                col = pos_idx * STRIDE + 1
                row = layer_idx * STRIDE + 1 + cumulative_extra

            gc = GridCoord(col=col, row=row)

            # Collision check: shift perpendicular if occupied
            while not _can_place(layout, gc):
                if direction.is_horizontal:
                    gc = GridCoord(col=gc.col, row=gc.row + STRIDE)
                else:
                    gc = GridCoord(col=gc.col + STRIDE, row=gc.row)

            placement = NodePlacement(node_id=nid, grid=gc)
            layout.placements[nid] = placement

            # Reserve 3x3 block
            for dc in range(-1, 2):
                for dr in range(-1, 2):
                    layout.grid_occupied[(gc.col + dc, gc.row + dr)] = nid


def _can_place(layout: GridLayout, gc: GridCoord) -> bool:
    """Check if a 3x3 block centered at gc is free."""
    for dc in range(-1, 2):
        for dr in range(-1, 2):
            if not layout.is_free(gc.col + dc, gc.row + dr):
                return False
    return True


def _word_wrap(text: str, max_width: int) -> list[str]:
    """Split text at word boundaries, keeping lines under max_width."""
    words = text.split()
    if not words:
        return [text]

    lines: list[str] = []
    current_line = words[0]

    for word in words[1:]:
        if display_width(current_line) + 1 + display_width(word) <= max_width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


def normalize_sizes(graph: Graph, layout: GridLayout) -> None:
    """Normalize node dimensions within the same layer, capped at a maximum.

    Nodes at the same flow level (same layer) are normalized to the same
    perpendicular dimension so side-by-side nodes look consistent.
    """
    direction = graph.direction.normalized()

    # Group placements by layer
    layer_groups: dict[int, list[NodePlacement]] = {}
    for nid, p in layout.placements.items():
        # Skip junctions from normalization
        node = graph.nodes.get(nid)
        if node and node.shape == NodeShape.JUNCTION:
            continue
        if direction.is_vertical:
            layer_key = p.grid.row  # same row = same layer in TD
        else:
            layer_key = p.grid.col  # same col = same layer in LR
        layer_groups.setdefault(layer_key, []).append(p)

    for placements in layer_groups.values():
        if len(placements) < 2:
            continue  # single node in layer, nothing to normalize

        if direction.is_vertical:
            # TD: normalize column widths within same layer
            cols = {p.grid.col for p in placements}
            max_w = max(layout.col_widths.get(c, 1) for c in cols)
            target = min(max_w, MAX_NORMALIZED_WIDTH)
            for c in cols:
                layout.col_widths[c] = max(layout.col_widths.get(c, 1), target)
        else:
            # LR: normalize row heights within same layer
            rows = {p.grid.row for p in placements}
            max_h = max(layout.row_heights.get(r, 1) for r in rows)
            target = min(max_h, MAX_NORMALIZED_HEIGHT)
            for r in rows:
                layout.row_heights[r] = max(layout.row_heights.get(r, 1), target)


def compute_sizes(
    graph: Graph,
    layout: GridLayout,
    padding_x: int,
    padding_y: int,
    gap: int = 4,
) -> None:
    """Compute column widths and row heights based on node content."""
    for nid, placement in layout.placements.items():
        node = graph.nodes[nid]

        # Minimal-size nodes (junctions) -- just 1x1
        if node.shape == NodeShape.JUNCTION:
            col = placement.grid.col
            row = placement.grid.row
            layout.col_widths[col] = max(layout.col_widths.get(col, 1), 1)
            layout.row_heights[row] = max(layout.row_heights.get(row, 1), 1)
            continue

        label = node.label
        lines = label.split("\\n") if "\\n" in label else [label]

        # Word-wrap lines that exceed max width
        wrapped_lines: list[str] = []
        for line in lines:
            if display_width(line) <= MAX_LABEL_WIDTH:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(_word_wrap(line, MAX_LABEL_WIDTH))

        # Update the node's label with wrapped text
        if len(wrapped_lines) > 1 and wrapped_lines != lines:
            node.label = "\\n".join(wrapped_lines)

        text_width = max(display_width(l) for l in wrapped_lines) if wrapped_lines else 0
        text_height = len(wrapped_lines)

        content_width = text_width + padding_x  # padding on each side
        content_height = text_height + padding_y  # padding top/bottom

        # Ensure minimum sizes
        content_width = max(content_width, 3)
        content_height = max(content_height, 3)

        col = placement.grid.col
        row = placement.grid.row

        # Center column gets the content width
        cur = layout.col_widths.get(col, 1)
        layout.col_widths[col] = max(cur, content_width)

        # Center row gets the content height
        cur = layout.row_heights.get(row, 1)
        layout.row_heights[row] = max(cur, content_height)

    # Border cells (around nodes) get width 1
    all_cols: set[int] = set()
    all_rows: set[int] = set()
    for placement in layout.placements.values():
        c, r = placement.grid.col, placement.grid.row
        for dc in range(-1, 2):
            all_cols.add(c + dc)
        for dr in range(-1, 2):
            all_rows.add(r + dr)

    for c in all_cols:
        if c not in layout.col_widths:
            layout.col_widths[c] = 1
    for r in all_rows:
        if r not in layout.row_heights:
            layout.row_heights[r] = 1

    # Gap cells between nodes
    max_col = max(all_cols) if all_cols else 0
    max_row = max(all_rows) if all_rows else 0
    for c in range(max_col + 2):
        if c not in layout.col_widths:
            layout.col_widths[c] = gap  # gap columns
    for r in range(max_row + 2):
        if r not in layout.row_heights:
            layout.row_heights[r] = max(gap - 1, 1)  # gap rows

    # Expand gaps to fit edge labels
    _expand_gaps_for_edge_labels(graph, layout)


def _expand_gaps_for_edge_labels(graph: Graph, layout: GridLayout) -> None:
    """Expand gap cells between nodes to fit edge labels.

    For horizontal flow (LR): expand gap columns so labels fit on
    horizontal segments.  For vertical flow (TB): expand gap rows so
    labels fit beside vertical segments.
    """
    direction = graph.direction.normalized()
    is_horizontal = direction.is_horizontal

    for edge in graph.edges:
        if not edge.label:
            continue
        label_len = display_width(edge.label)

        src_p = layout.placements.get(edge.source)
        tgt_p = layout.placements.get(edge.target)
        if not src_p or not tgt_p:
            continue

        if is_horizontal:
            # Edges run horizontally -- label needs gap column width
            c1 = min(src_p.grid.col, tgt_p.grid.col)
            c2 = max(src_p.grid.col, tgt_p.grid.col)
            # Gap cells are between the two node 3x3 blocks
            gap_start = c1 + 2
            gap_end = c2 - 2
            if gap_start > gap_end:
                continue
            # Need: gap_width + 1 >= label_len + 2  ->  gap_width >= label_len + 1
            needed = label_len + 1
            # Distribute across first gap cell (simplest approach)
            cur = layout.col_widths.get(gap_start, 4)
            layout.col_widths[gap_start] = max(cur, needed)
        else:
            # Edges run vertically -- label placed beside the line (x+1)
            # Expand gap row for vertical space, but also ensure the gap
            # column is wide enough for the label text beside the line
            r1 = min(src_p.grid.row, tgt_p.grid.row)
            r2 = max(src_p.grid.row, tgt_p.grid.row)
            gap_start = r1 + 2
            gap_end = r2 - 2
            if gap_start > gap_end:
                continue
            # Need enough vertical space: at least 2 rows for the label
            cur = layout.row_heights.get(gap_start, 3)
            layout.row_heights[gap_start] = max(cur, 3)

            # Also ensure the gap column beside the edge is wide enough
            # for the label text. The edge typically runs in a border col;
            # the label is placed at x+1, which falls in the gap col after.
            # Determine gap column from both source AND target positions.
            src_col = src_p.grid.col
            tgt_col = tgt_p.grid.col
            # The edge runs vertically in a gap column between src and tgt.
            # Expand all gap columns that might hold the label.
            gap_cols: set[int] = set()
            if tgt_col >= src_col:
                gap_cols.add(src_col + 2)  # gap to the right of source
            if tgt_col <= src_col:
                gap_cols.add(src_col - 2)  # gap to the left of source
            # For edges crossing multiple columns, also expand intermediate gaps
            c_min = min(src_col, tgt_col)
            c_max = max(src_col, tgt_col)
            for c in range(c_min + 2, c_max, STRIDE):
                gap_cols.add(c)
            for gap_col in gap_cols:
                if gap_col >= 0 and gap_col in layout.col_widths:
                    cur = layout.col_widths[gap_col]
                    layout.col_widths[gap_col] = max(cur, label_len + 1)

    # For vertical flow: when multiple labeled edges leave the same source,
    # ensure the gap row is tall enough for all labels with spacing.
    if not is_horizontal:
        from collections import Counter
        labeled_per_src: Counter[str] = Counter()
        for edge in graph.edges:
            if edge.label:
                labeled_per_src[edge.source] += 1
        for src_id, count in labeled_per_src.items():
            if count < 2:
                continue
            src_p = layout.placements.get(src_id)
            if not src_p:
                continue
            gap_row = src_p.grid.row + 2
            needed = count * 2 + 1  # 2 rows per label + spacing
            cur = layout.row_heights.get(gap_row, 3)
            layout.row_heights[gap_row] = max(cur, needed)
