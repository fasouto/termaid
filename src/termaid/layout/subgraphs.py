"""Subgraph layout handling for the layout engine.

Manages gap expansion for subgraph borders and labels,
and computes subgraph bounding boxes after node placement.
"""
from __future__ import annotations

from ..graph.model import Direction, Graph, Subgraph
from .grid import (
    SG_BORDER_PAD,
    SG_GAP_PER_LEVEL,
    SG_LABEL_HEIGHT,
    GridLayout,
    SubgraphBounds,
)


def expand_gaps_for_subgraphs(
    graph: Graph, layout: GridLayout, direction: Direction,
) -> None:
    """Expand gap cells to accommodate subgraph borders, labels, and nesting."""
    if not graph.subgraphs:
        return

    # Compute nesting depth for each node
    def _get_depth(nid: str) -> int:
        depth = 0
        sg = graph.find_subgraph_for_node(nid)
        while sg:
            depth += 1
            sg = sg.parent
        return depth

    node_depths = {nid: _get_depth(nid) for nid in graph.node_order}

    is_vertical = direction in (Direction.TB, Direction.TD)

    # Group nodes by flow-axis (layer) and cross-axis grid positions
    flow_groups: dict[int, list[str]] = {}
    cross_groups: dict[int, list[str]] = {}
    for nid, p in layout.placements.items():
        flow_pos = p.grid.row if is_vertical else p.grid.col
        cross_pos = p.grid.col if is_vertical else p.grid.row
        flow_groups.setdefault(flow_pos, []).append(nid)
        cross_groups.setdefault(cross_pos, []).append(nid)

    sorted_flow = sorted(flow_groups.keys())
    sorted_cross = sorted(cross_groups.keys())

    # --- Expand flow-direction gaps (between layers) ---
    for i in range(len(sorted_flow) - 1):
        pos1 = sorted_flow[i]
        pos2 = sorted_flow[i + 1]

        min_depth1 = min(node_depths[nid] for nid in flow_groups[pos1])
        max_depth2 = max(node_depths[nid] for nid in flow_groups[pos2])
        entering = max(0, max_depth2 - min_depth1)

        min_depth2 = min(node_depths[nid] for nid in flow_groups[pos2])
        max_depth1 = max(node_depths[nid] for nid in flow_groups[pos1])
        exiting = max(0, max_depth1 - min_depth2)

        depth_change = max(entering, exiting)

        # Detect sibling subgraph transitions: when adjacent layers are in
        # different subgraphs at the same depth, we need to exit one and
        # enter the other (2 boundary crossings, not 0).
        if depth_change == 0:
            sg_ids1 = {sg.id for nid in flow_groups[pos1] if (sg := graph.find_subgraph_for_node(nid))}
            sg_ids2 = {sg.id for nid in flow_groups[pos2] if (sg := graph.find_subgraph_for_node(nid))}
            if sg_ids1 and sg_ids2 and sg_ids1 != sg_ids2:
                # Exiting one subgraph and entering another at same depth
                depth_change = 2

        if depth_change > 0:
            extra = depth_change * SG_GAP_PER_LEVEL
            # Gap cells between the two node rows/columns
            gap_start = pos1 + 2
            gap_end = pos2 - 2
            for gap in range(gap_start, gap_end + 1):
                if is_vertical:
                    cur = layout.row_heights.get(gap, 1)
                    layout.row_heights[gap] = max(cur, extra)
                else:
                    cur = layout.col_widths.get(gap, 2)
                    layout.col_widths[gap] = max(cur, extra)

    # --- Expand cross-direction gaps (sibling subgraphs) ---
    for i in range(len(sorted_cross) - 1):
        pos1 = sorted_cross[i]
        pos2 = sorted_cross[i + 1]

        inner1: set[str] = set()
        for nid in cross_groups[pos1]:
            sg = graph.find_subgraph_for_node(nid)
            if sg:
                inner1.add(sg.id)

        inner2: set[str] = set()
        for nid in cross_groups[pos2]:
            sg = graph.find_subgraph_for_node(nid)
            if sg:
                inner2.add(sg.id)

        if (inner1 or inner2) and inner1 != inner2:
            extra = 8  # Space for two subgraph borders + gap
            gap_start = pos1 + 2
            gap_end = pos2 - 2
            for gap in range(gap_start, gap_end + 1):
                if is_vertical:
                    cur = layout.col_widths.get(gap, 2)
                    layout.col_widths[gap] = max(cur, extra)
                else:
                    cur = layout.row_heights.get(gap, 1)
                    layout.row_heights[gap] = max(cur, extra)


def compute_subgraph_bounds(
    graph: Graph,
    layout: GridLayout,
) -> None:
    """Compute bounding boxes for subgraphs."""
    def _compute(sg: Subgraph) -> SubgraphBounds | None:
        # Recursively compute children first
        child_bounds: list[SubgraphBounds] = []
        for child in sg.children:
            cb = _compute(child)
            if cb:
                child_bounds.append(cb)
                layout.subgraph_bounds.append(cb)

        # Gather all node placements in this subgraph
        all_node_ids = set(sg.node_ids)
        for child in sg.children:
            all_node_ids.update(child.node_ids)
            _gather_all_nodes(child, all_node_ids)

        if not all_node_ids and not child_bounds:
            return None

        min_x = float("inf")
        min_y = float("inf")
        max_x = 0
        max_y = 0

        for nid in all_node_ids:
            if nid in layout.placements:
                p = layout.placements[nid]
                min_x = min(min_x, p.draw_x)
                min_y = min(min_y, p.draw_y)
                max_x = max(max_x, p.draw_x + p.draw_width)
                max_y = max(max_y, p.draw_y + p.draw_height)

        for cb in child_bounds:
            min_x = min(min_x, cb.x)
            min_y = min(min_y, cb.y)
            max_x = max(max_x, cb.x + cb.width)
            max_y = max(max_y, cb.y + cb.height)

        if min_x == float("inf"):
            return None

        content_width = int(max_x - min_x) + SG_BORDER_PAD * 2
        label_width = len(sg.label) + 4
        final_width = max(content_width, label_width)

        bounds = SubgraphBounds(
            subgraph=sg,
            x=int(min_x) - SG_BORDER_PAD,
            y=int(min_y) - SG_BORDER_PAD - SG_LABEL_HEIGHT,
            width=final_width,
            height=int(max_y - min_y) + SG_BORDER_PAD * 2 + SG_LABEL_HEIGHT,
        )
        return bounds

    for sg in graph.subgraphs:
        bounds = _compute(sg)
        if bounds:
            layout.subgraph_bounds.append(bounds)


def _gather_all_nodes(sg: Subgraph, result: set[str]) -> None:
    """Recursively gather all node IDs from a subgraph and its children."""
    result.update(sg.node_ids)
    for child in sg.children:
        _gather_all_nodes(child, result)
