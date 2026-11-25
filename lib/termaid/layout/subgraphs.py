"""Subgraph layout handling for the layout engine.

Manages gap expansion for subgraph borders and labels,
and computes subgraph bounding boxes after node placement.
"""
from __future__ import annotations

from ..graph.model import Direction, Graph, Subgraph
from ..utils import display_width
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

    # Ancestor subgraph chain for each node
    def _get_chain(nid: str) -> frozenset[str]:
        chain: set[str] = set()
        sg = graph.find_subgraph_for_node(nid)
        while sg:
            chain.add(sg.id)
            sg = sg.parent
        return frozenset(chain)

    node_chains = {nid: _get_chain(nid) for nid in graph.node_order}

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

        # Count subgraph borders that live in this gap: a subgraph
        # containing nodes on one side but not the other has a border
        # (bottom or top) between the two layers. The symmetric difference
        # of the ancestor sets counts exactly those borders, covering
        # nesting transitions and sibling subgraphs alike.
        sgs1: set[str] = set()
        for nid in flow_groups[pos1]:
            sgs1 |= node_chains[nid]
        sgs2: set[str] = set()
        for nid in flow_groups[pos2]:
            sgs2 |= node_chains[nid]
        depth_change = len(sgs1 ^ sgs2)

        if depth_change > 0:
            extra = depth_change * SG_GAP_PER_LEVEL
            # Gap cells between the two node rows/columns
            gap_start = pos1 + 2
            gap_end = pos2 - 2
            # The borders sit at the ends of the gap, so with several cells
            # the first one keeps room below the upper border and the last
            # one room above the lower border and its label.
            sizes = {gap_start: extra // 2 + 1, gap_end: extra}
            for gap, size in sizes.items():
                if is_vertical:
                    cur = layout.row_heights.get(gap, 1)
                    layout.row_heights[gap] = max(cur, size)
                else:
                    cur = layout.col_widths.get(gap, 2)
                    layout.col_widths[gap] = max(cur, size)

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
    title_caps: dict[str, int] | None = None,
) -> None:
    """Compute bounding boxes for subgraphs.

    *title_caps* maps a subgraph id to the widest its title may make its box.
    """
    title_caps = title_caps or {}
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

        # A straight vertical edge inside the box gets its label on the
        # left of its line, so the box holds that label as content.
        for edge in graph.edges:
            src = layout.placements.get(edge.source)
            tgt = layout.placements.get(edge.target)
            if (
                edge.label and src and tgt
                and edge.source in all_node_ids and edge.target in all_node_ids
                and src.grid.col == tgt.grid.col and src.grid.row != tgt.grid.row
            ):
                line_x, _ = layout.grid_to_draw_center(src.grid.col, 0)
                text_width = max(display_width(line) for line in edge.label.split("\n"))
                min_x = min(min_x, line_x - text_width)

        content_width = int(max_x - min_x) + SG_BORDER_PAD * 2
        label_width = display_width(sg.label) + 4
        final_width = max(content_width, min(label_width, title_caps.get(sg.id, label_width)))

        bounds = SubgraphBounds(
            subgraph=sg,
            x=int(min_x) - SG_BORDER_PAD,
            y=int(min_y) - SG_BORDER_PAD - SG_LABEL_HEIGHT,
            width=final_width,
            height=int(max_y - min_y) + SG_BORDER_PAD * 2 + SG_LABEL_HEIGHT,
            content_width=content_width,
        )
        return bounds

    for sg in graph.subgraphs:
        bounds = _compute(sg)
        if bounds:
            layout.subgraph_bounds.append(bounds)


_TITLE_CLEARANCE = 3  # cells between a box's side and a neighbour, room for `─►`


def fit_titles(graph: Graph, layout: GridLayout) -> None:
    """Narrow a subgraph box that its title stretched onto a neighbour.

    A box grows rightwards to fit a title wider than its nodes. Where that
    would cover a node or box outside the subgraph, the box stops short of
    that neighbour, never narrower than its nodes need, and the title is
    clipped when drawn. A nested box that narrows lets its parent narrow
    too, so this repeats, at most once per subgraph.
    """
    caps: dict[str, int] = {}
    for _ in range(len(layout.subgraph_bounds)):
        changed = False
        for sb in layout.subgraph_bounds:
            if sb.width <= sb.content_width:
                continue
            members: set[str] = set()
            _gather_all_nodes(sb.subgraph, members)
            content_side = sb.x + sb.content_width - 1
            reach = sb.x + sb.width + 1  # a neighbour may sit one cell off the side
            lefts = [
                p.draw_x for nid, p in layout.placements.items()
                if nid not in members
                and p.draw_y < sb.y + sb.height and sb.y < p.draw_y + p.draw_height
                and content_side < p.draw_x < reach
            ]
            lefts += [
                other.x for other in layout.subgraph_bounds
                if not _nested(sb.subgraph, other.subgraph)
                and other.y < sb.y + sb.height and sb.y < other.y + other.height
                and content_side < other.x < reach
            ]
            if lefts:
                caps[sb.subgraph.id] = max(sb.content_width, min(lefts) - _TITLE_CLEARANCE - sb.x)
                changed = True
        if not changed:
            return
        layout.subgraph_bounds.clear()
        compute_subgraph_bounds(graph, layout, caps)


def _nested(a: Subgraph, b: Subgraph) -> bool:
    """Whether one of the two subgraphs holds the other, or they are one."""
    for inner, outer in ((a, b), (b, a)):
        sg: Subgraph | None = inner
        while sg:
            if sg is outer:
                return True
            sg = sg.parent
    return False


def _gather_all_nodes(sg: Subgraph, result: set[str]) -> None:
    """Recursively gather all node IDs from a subgraph and its children."""
    result.update(sg.node_ids)
    for child in sg.children:
        _gather_all_nodes(child, result)
