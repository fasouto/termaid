"""Node placement and sizing for the layout engine.

Handles placing nodes on the grid, computing column widths and row
heights based on label content, and normalizing sizes within layers.
"""
from __future__ import annotations

from ..graph.model import Direction, Graph
from ..graph.shapes import NodeShape
from ..utils import display_width, wrap_display_text
from .grid import (
    STRIDE,
    MAX_LABEL_WIDTH,
    MAX_NORMALIZED_WIDTH,
    GridCoord,
    GridLayout,
    NodePlacement,
)



def _aligned_slots(graph: Graph, layer_order: list[list[str]]) -> dict[str, int]:
    """Pick a cross-axis slot for every node so edges run as straight as possible.

    ``layer_order`` fixes the order of the nodes in each layer; this only
    decides how far along the cross axis each one sits. A node wants the
    mean slot of its parents in the previous layer, and a parent wants the
    mean slot of its children, so the slots are settled by sweeping down
    and up a few times. Within a layer slots stay strictly increasing, so
    the order never changes and nothing overlaps.

    Without this every layer is packed from slot 0, so a node whose only
    parent is in row 2 lands in row 0 next to some unrelated node, and the
    diagram reads as if they were connected (issue #14).

    Graphs with subgraphs keep packed slots: subgraph boxes are drawn
    around their members, and spreading members apart to line them up
    with outside nodes makes those boxes collide.
    """
    slots = {nid: i for nodes in layer_order for i, nid in enumerate(nodes)}
    if graph.subgraphs or graph.grid_positions or len(layer_order) < 2:
        return slots
    layer_of = {nid: li for li, nodes in enumerate(layer_order) for nid in nodes}
    parents: dict[str, list[str]] = {nid: [] for nid in slots}
    children: dict[str, list[str]] = {nid: [] for nid in slots}
    for edge in graph.edges:
        if layer_of.get(edge.target, -1) == layer_of.get(edge.source, -2) + 1:
            parents[edge.target].append(edge.source)
            children[edge.source].append(edge.target)

    def _sweep(order: list[list[str]], neighbours: dict[str, list[str]]) -> None:
        for nodes in order:
            if not nodes:
                # A longer link (A ---> B) leaves its middle ranks empty.
                continue
            wants: list[float] = []
            for nid in nodes:
                anchors = [slots[n] for n in neighbours[nid]]
                wants.append(sum(anchors) / len(anchors) if anchors else (wants[-1] + 1 if wants else 0))
            # Place left to right, then slide each run of nodes that pushed on
            # each other back so the run is centred on what it wanted. Without
            # the centring a group that wants one slot lands to its right, the
            # other layer follows it, and every sweep drifts a slot further.
            placed: list[int] = []
            run_start = 0
            for i, want in enumerate(wants):
                # Floor, not round: a parent over two children wants a half
                # slot, and rounding it up would creep right on every sweep.
                slot = max(int(want), placed[-1] + 1 if placed else 0)
                if placed and slot > placed[-1] + 1:
                    _centre(placed, wants, run_start, i)
                    run_start = i
                placed.append(slot)
            _centre(placed, wants, run_start, len(placed))
            for nid, slot in zip(nodes, placed):
                slots[nid] = slot

    def _centre(placed: list[int], wants: list[float], start: int, end: int) -> None:
        overshoot = sum(placed[i] - wants[i] for i in range(start, end)) / (end - start)
        floor = placed[start - 1] + 1 if start else 0
        shift = min(int(overshoot), placed[start] - floor)
        for i in range(start, end):
            placed[i] -= shift

    for _ in range(3):
        _sweep(layer_order[1:], parents)
        _sweep(layer_order[-2::-1], children)
    lowest = min(slots.values())
    return {nid: slot - lowest for nid, slot in slots.items()}


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
    slots = _aligned_slots(graph, layer_order)
    cumulative_extra = 0
    for layer_idx, nodes in enumerate(layer_order):
        if layer_idx > 0:
            cumulative_extra += expansions.get(layer_idx - 1, 0)
        layout.layer_coords.append(layer_idx * STRIDE + 1 + cumulative_extra)
        for nid in nodes:
            pos_idx = slots[nid]
            if direction.is_horizontal:
                col = layout.layer_coords[-1]
                row = pos_idx * STRIDE + 1
            else:
                col = pos_idx * STRIDE + 1
                row = layout.layer_coords[-1]

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


def normalize_sizes(graph: Graph, layout: GridLayout) -> None:
    """Normalize node widths within the same layer of a TD/BT graph, capped at a maximum.

    Nodes at the same flow level sit side by side in TD, so they get the same
    width. In LR they are stacked, and each keeps the height of its own label,
    as in Mermaid: padding every box in a column to the tallest one makes
    the whole diagram much taller.
    """
    direction = graph.direction.normalized()
    if not direction.is_vertical:
        return

    # Group placements by layer
    layer_groups: dict[int, list[NodePlacement]] = {}
    for nid, p in layout.placements.items():
        # Skip junctions from normalization
        node = graph.nodes.get(nid)
        if node and node.shape == NodeShape.JUNCTION:
            continue
        layer_groups.setdefault(p.grid.row, []).append(p)  # same row = same layer

    for placements in layer_groups.values():
        if len(placements) < 2:
            continue  # single node in layer, nothing to normalize

        cols = {p.grid.col for p in placements}
        max_w = max(layout.col_widths.get(c, 1) for c in cols)
        target = min(max_w, MAX_NORMALIZED_WIDTH)
        for c in cols:
            layout.col_widths[c] = max(layout.col_widths.get(c, 1), target)


def compute_sizes(
    graph: Graph,
    layout: GridLayout,
    padding_x: int,
    padding_y: int,
    gap: int = 4,
    max_label_width: int | None = None,
) -> None:
    """Compute column widths and row heights based on node content.

    Node label lines wider than ``max_label_width`` (default
    ``MAX_LABEL_WIDTH``) are wrapped at word boundaries. Edge labels wrap
    only when a width is given, into newline-joined lines.
    """
    if max_label_width is None:
        max_label_width = MAX_LABEL_WIDTH
    else:
        for edge in graph.edges:
            # Measured per line: a <br> in the label has already split it.
            if any(display_width(line) > max_label_width for line in edge.label.split("\n")):
                edge.label = "\n".join(
                    wrap_display_text(edge.label, max_label_width, hard_break=False)
                )
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

        wrapped_lines: list[str] = []
        for line in lines:
            if display_width(line) <= max_label_width:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(wrap_display_text(line, max_label_width, hard_break=False))

        # Update the node's label with wrapped text
        if len(wrapped_lines) > 1 and wrapped_lines != lines:
            node.label = "\\n".join(wrapped_lines)

        text_width = max(display_width(l) for l in wrapped_lines) if wrapped_lines else 0
        text_height = len(wrapped_lines)

        content_width = text_width + padding_x  # padding on each side
        content_height = text_height + padding_y  # padding top/bottom

        # Ensure minimum sizes
        content_width = max(content_width, 3)
        content_height = max(content_height, 1)

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

    _expand_gaps_for_turns(graph, layout)

    # Expand gaps to fit edge labels
    _expand_gaps_for_edge_labels(graph, layout)


_MIN_TURN_GAP = 3


def _expand_gaps_for_turns(graph: Graph, layout: GridLayout) -> None:
    vertical = graph.direction.normalized().is_vertical
    for edge in graph.edges:
        src = layout.placements.get(edge.source)
        tgt = layout.placements.get(edge.target)
        if not src or not tgt or edge.is_self_reference:
            continue
        if vertical and tgt.grid.row > src.grid.row and tgt.grid.col != src.grid.col:
            last_gap_row = tgt.grid.row - 2
            layout.row_heights[last_gap_row] = max(layout.row_heights.get(last_gap_row, 1), _MIN_TURN_GAP)
        elif not vertical and tgt.grid.col > src.grid.col and tgt.grid.row != src.grid.row:
            last_gap_col = tgt.grid.col - 2
            layout.col_widths[last_gap_col] = max(layout.col_widths.get(last_gap_col, 1), _MIN_TURN_GAP)


def _expand_gaps_for_edge_labels(graph: Graph, layout: GridLayout) -> None:
    """Expand gap cells between nodes to fit edge labels.

    For horizontal flow (LR): expand gap columns so labels fit on
    horizontal segments.  For vertical flow (TB): expand gap rows so
    labels fit beside vertical segments.  A wrapped label counts as a
    block: its widest line and its line count.
    """
    direction = graph.direction.normalized()
    is_horizontal = direction.is_horizontal

    for edge in graph.edges:
        if not edge.label:
            continue
        lines = edge.label.split("\n")
        label_len = max(display_width(line) for line in lines)

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
            if len(lines) == 1:
                continue
            if src_p.grid.row != tgt_p.grid.row:
                # A block beside the vertical run through the middle of the
                # gap column needs its width on one side and its line count
                # in the gap row between the lanes.
                layout.col_widths[gap_start] = max(layout.col_widths[gap_start], 2 * label_len + 2)
                gap_row = min(src_p.grid.row, tgt_p.grid.row) + 2
                layout.row_heights[gap_row] = max(layout.row_heights.get(gap_row, 1), len(lines))
            # A block above the segment needs its line count in rows: the
            # lane's upper half and border row, then the gap row above, or
            # the canvas top for the first lane.
            for r in {src_p.grid.row, tgt_p.grid.row}:
                above = layout.row_heights.get(r, 1) // 2 + 1
                gap_row = r - 2
                if gap_row < 0:
                    layout.offset_y = max(layout.offset_y, len(lines) - above)
                else:
                    layout.row_heights[gap_row] = max(layout.row_heights.get(gap_row, 1), len(lines) - above)
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
            layout.row_heights[gap_start] = max(cur, 3, len(lines))

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
        rows_per_src: Counter[str] = Counter()
        for edge in graph.edges:
            if edge.label:
                labeled_per_src[edge.source] += 1
                rows_per_src[edge.source] += edge.label.count("\n") + 2
        for src_id, count in labeled_per_src.items():
            if count < 2:
                continue
            src_p = layout.placements.get(src_id)
            if not src_p:
                continue
            gap_row = src_p.grid.row + 2
            needed = rows_per_src[src_id] + 1  # each label's rows + spacing
            cur = layout.row_heights.get(gap_row, 3)
            layout.row_heights[gap_row] = max(cur, needed)
