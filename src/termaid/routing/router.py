"""Edge routing orchestrator.

Determines start/end attachment points on nodes, runs A* pathfinding,
and handles direction selection (preferred vs alternative paths).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from ..graph.model import Direction, Edge, Graph
from ..layout.grid import GridLayout, NodePlacement, SubgraphBounds
from .pathfinder import find_path, simplify_path


class AttachDir(Enum):
    TOP = auto()
    BOTTOM = auto()
    LEFT = auto()
    RIGHT = auto()


@dataclass
class RoutedEdge:
    """An edge with its computed path in grid coordinates."""
    edge: Edge
    # Path as grid coordinates (simplified to corners)
    grid_path: list[tuple[int, int]] = field(default_factory=list)
    # Path as drawing coordinates
    draw_path: list[tuple[int, int]] = field(default_factory=list)
    start_dir: AttachDir = AttachDir.RIGHT
    end_dir: AttachDir = AttachDir.LEFT
    label: str = ""
    index: int = 0
    # Grid cells occupied by this edge's path
    occupied_cells: set[tuple[int, int]] = field(default_factory=set)


def route_edges(graph: Graph, layout: GridLayout) -> list[RoutedEdge]:
    """Route all edges in the graph."""
    direction = graph.direction.normalized()
    routed: list[RoutedEdge] = []
    soft_obstacles: set[tuple[int, int]] = set()

    # Build subgraph bounds lookup
    sg_bounds: dict[str, SubgraphBounds] = {}
    for sb in layout.subgraph_bounds:
        sg_bounds[sb.subgraph.id] = sb

    # Grid regions of each subgraph box: edges that neither start nor end
    # in a subgraph should avoid routing through its box.
    sg_regions = _compute_sg_regions(layout, sg_bounds)

    for i, edge in enumerate(graph.edges):
        src, tgt = _resolve_endpoints(edge, layout, sg_bounds)

        if src is None or tgt is None:
            continue

        if edge.is_self_reference and not edge.source_is_subgraph:
            re = _route_self_edge(edge, src, layout, direction)
            re.index = i
            routed.append(re)
            continue

        forbidden = _foreign_sg_cells(edge, graph, sg_regions)
        re = _route_edge(edge, src, tgt, layout, direction, soft_obstacles | forbidden)
        re.index = i
        soft_obstacles.update(re.occupied_cells)

        # Snap subgraph-endpoint edges onto the subgraph border so they
        # attach to the box, not to the inner node used for routing.
        if edge.source_is_subgraph and edge.source in sg_bounds:
            _clip_endpoint_to_box(re.draw_path, sg_bounds[edge.source], from_start=True)
        if edge.target_is_subgraph and edge.target in sg_bounds:
            _clip_endpoint_to_box(re.draw_path, sg_bounds[edge.target], from_start=False)

        routed.append(re)

    # Post-process: spread edges that share the same target endpoint so
    # arrows don't overlap on the same cell.  Start points are NOT spread
    # because edges diverge naturally from a shared T-junction, and
    # spreading the start creates jog segments at the border that produce
    # ┼ artifacts when the jog crosses the node border characters.
    _spread_shared_endpoints(routed, layout, sg_bounds)

    return routed


def _spread_shared_endpoints(
    routed: list[RoutedEdge],
    layout: GridLayout,
    sg_bounds: dict[str, SubgraphBounds],
) -> None:
    """Spread edges that share the same draw-path end point.

    When multiple edges converge on the same cell (e.g. two edges arriving
    at the center of a node's top border), offset them along the border so
    each edge gets its own arrow cell.
    """
    from collections import defaultdict

    end_groups: dict[tuple[int, int], list[RoutedEdge]] = defaultdict(list)
    for re in routed:
        if len(re.draw_path) >= 2:
            end_groups[re.draw_path[-1]].append(re)

    for point, edges in end_groups.items():
        if len(edges) <= 1:
            continue
        tgt_id = edges[0].edge.target
        tgt = layout.placements.get(tgt_id)
        if not tgt and tgt_id in sg_bounds:
            sb = sg_bounds[tgt_id]
            from ..layout.grid import GridCoord
            tgt = NodePlacement(
                node_id=tgt_id, grid=GridCoord(0, 0),
                draw_x=sb.x, draw_y=sb.y, draw_width=sb.width, draw_height=sb.height,
            )
        if not tgt:
            continue
        _apply_spread(edges, point, tgt, is_start=False)


def _apply_spread(
    edges: list[RoutedEdge],
    point: tuple[int, int],
    placement: NodePlacement,
    is_start: bool,
) -> None:
    """Offset each edge's endpoint along the node border.

    For TOP/BOTTOM attachment (horizontal spread): shifts the adjacent
    corner point to match the new x, avoiding backward horizontal jog
    segments that create stray line artifacts.

    For LEFT/RIGHT attachment (vertical spread): inserts a short
    perpendicular jog at the adjacent point's x so the last segment
    stays horizontal and the arrow direction is correct.
    """
    if is_start:
        return  # start spreading disabled; causes border artifacts

    n = len(edges)
    px, py = point
    attach = edges[0].end_dir

    if attach in (AttachDir.TOP, AttachDir.BOTTOM):
        # Vertical arrival: spread horizontally along the border.
        min_x = placement.draw_x + 1
        max_x = placement.draw_x + placement.draw_width - 2
        spread_range = max_x - min_x
        if spread_range < n - 1:
            return
        step = min(2, spread_range // max(n - 1, 1))
        for i, re in enumerate(edges):
            offset = int((i - (n - 1) / 2) * step)
            if offset == 0:
                continue
            new_x = max(min_x, min(max_x, px + offset))
            adj_x, adj_y = re.draw_path[-2]
            re.draw_path[-1] = (new_x, py)
            re.draw_path[-2] = (new_x, adj_y)
    else:
        # Horizontal arrival: spread vertically along the border.
        # Only spread when the approach segment is long enough to fit
        # a clean corner + line + arrow (>= 4 cells from the last turn
        # to the endpoint).  Tight gaps produce cramped ╭► patterns.
        min_y = placement.draw_y + 1
        max_y = placement.draw_y + placement.draw_height - 2
        spread_range = max_y - min_y
        if spread_range < n - 1:
            return
        # Check that all edges have enough approach distance
        min_gap = min(abs(px - re.draw_path[-2][0]) for re in edges)
        if min_gap < 4:
            return  # not enough room for clean corner + arrow
        step = min(2, spread_range // max(n - 1, 1))
        for i, re in enumerate(edges):
            offset = int((i - (n - 1) / 2) * step)
            if offset == 0:
                continue
            new_y = max(min_y, min(max_y, py + offset))
            adj_x, adj_y = re.draw_path[-2]
            re.draw_path[-1] = (px, new_y)
            re.draw_path.insert(-1, (adj_x, new_y))


def _sg_member_placements(
    sb: SubgraphBounds, layout: GridLayout,
) -> list[NodePlacement]:
    """Placements of all nodes inside a subgraph (recursively)."""
    member_ids: set[str] = set()

    def _gather(sg) -> None:
        member_ids.update(sg.node_ids)
        for child in sg.children:
            _gather(child)

    _gather(sb.subgraph)
    return [layout.placements[m] for m in member_ids if m in layout.placements]


def _resolve_endpoints(
    edge: Edge,
    layout: GridLayout,
    sg_bounds: dict[str, SubgraphBounds],
) -> tuple[NodePlacement | None, NodePlacement | None]:
    """Resolve edge endpoints to placements.

    For a subgraph endpoint, synthesize a virtual placement: the draw box
    is the subgraph's bounding box, and the grid cell is borrowed from a
    member node. When a subgraph is involved, the source and target cells
    are chosen jointly (closest member pair) so the edge crosses the box
    border on the facing side without jogs. The routed path is later
    clipped to the box border by ``_clip_endpoint_to_box``.
    """
    if not edge.source_is_subgraph and not edge.target_is_subgraph:
        return layout.placements.get(edge.source), layout.placements.get(edge.target)

    def _candidates(node_id: str, is_sg: bool) -> list[NodePlacement]:
        if not is_sg:
            p = layout.placements.get(node_id)
            return [p] if p else []
        sb = sg_bounds.get(node_id)
        if sb is None:
            return []
        return _sg_member_placements(sb, layout)

    src_cands = _candidates(edge.source, edge.source_is_subgraph)
    tgt_cands = _candidates(edge.target, edge.target_is_subgraph)
    if not src_cands or not tgt_cands:
        return None, None

    def _center(p: NodePlacement) -> tuple[int, int]:
        return (p.draw_x + p.draw_width // 2, p.draw_y + p.draw_height // 2)

    best_s, best_t = min(
        ((s, t) for s in src_cands for t in tgt_cands),
        key=lambda pair: (
            abs(_center(pair[0])[0] - _center(pair[1])[0])
            + abs(_center(pair[0])[1] - _center(pair[1])[1]),
            pair[0].node_id,
            pair[1].node_id,
        ),
    )

    from ..layout.grid import GridCoord

    def _virtualize(node_id: str, is_sg: bool, member: NodePlacement) -> NodePlacement:
        if not is_sg:
            return member
        sb = sg_bounds[node_id]
        return NodePlacement(
            node_id=node_id,
            grid=GridCoord(col=member.grid.col, row=member.grid.row),
            draw_x=sb.x,
            draw_y=sb.y,
            draw_width=sb.width,
            draw_height=sb.height,
        )

    return (
        _virtualize(edge.source, edge.source_is_subgraph, best_s),
        _virtualize(edge.target, edge.target_is_subgraph, best_t),
    )


def _clip_endpoint_to_box(
    draw_path: list[tuple[int, int]],
    sb: SubgraphBounds,
    from_start: bool,
) -> None:
    """Snap one end of a draw path onto a subgraph's border rectangle.

    The path was routed from a member node inside the box; drop the part
    inside the box and move the terminal point to where the path crosses
    the border, so the edge visually attaches to the subgraph itself.
    """
    if len(draw_path) < 2:
        return

    pts = draw_path if from_start else draw_path[::-1]
    x0, y0 = sb.x, sb.y
    x1, y1 = sb.x + sb.width - 1, sb.y + sb.height - 1

    def strictly_inside(p: tuple[int, int]) -> bool:
        return x0 < p[0] < x1 and y0 < p[1] < y1

    k = 0
    while k < len(pts) and strictly_inside(pts[k]):
        k += 1
    if k >= len(pts):
        return  # path never leaves the box; keep as-is

    if k == 0:
        # Terminal point is already on/outside the border: pull it back
        # onto the box edge along the first segment's axis.
        ax, ay = pts[0]
        bx, by = pts[1]
        if ax == bx:
            new = [(ax, min(max(ay, y0), y1))] + pts[1:]
        else:
            new = [(min(max(ax, x0), x1), ay)] + pts[1:]
    else:
        # Crossing point on the segment pts[k-1] (inside) -> pts[k] (outside).
        px, py = pts[k - 1]
        qx, qy = pts[k]
        if px == qx:
            cross = (px, y1 if qy > py else y0)
        else:
            cross = (x1 if qx > px else x0, py)
        new = [cross] + pts[k:]

    if len(new) >= 2 and new[0] == new[1]:
        new = new[1:]
    if len(new) < 2:
        return  # degenerate; keep the original path

    # If the last turn sits right next to the border, the terminal segment
    # has no room for the arrowhead/tee plus a line cell. Shift the turn
    # segment away from the border to open up the approach.
    if len(new) >= 4:
        (cx, cy), (nx, ny), (mx, my) = new[0], new[1], new[2]
        px, py = new[3]
        if cx == nx and ny == my and abs(cy - ny) < 3:
            # Perpendicular jog before a vertical approach
            sign = 1 if cy > ny else -1
            new_y = cy - 3 * sign
            if (sign > 0 and py < new_y) or (sign < 0 and py > new_y):
                new[1] = (nx, new_y)
                new[2] = (mx, new_y)
        elif cy == ny and nx == mx and abs(cx - nx) < 3:
            # Perpendicular jog before a horizontal approach
            sign = 1 if cx > nx else -1
            new_x = cx - 3 * sign
            if (sign > 0 and px < new_x) or (sign < 0 and px > new_x):
                new[1] = (new_x, ny)
                new[2] = (new_x, my)

    if not from_start:
        new = new[::-1]
    draw_path[:] = new


def _compute_sg_regions(
    layout: GridLayout,
    sg_bounds: dict[str, SubgraphBounds],
) -> dict[str, set[tuple[int, int]]]:
    """Grid cells covered by each subgraph box (member blocks + border channels)."""
    regions: dict[str, set[tuple[int, int]]] = {}
    for sg_id, sb in sg_bounds.items():
        members = _sg_member_placements(sb, layout)
        if not members:
            continue
        min_col = min(p.grid.col for p in members) - 1
        max_col = max(p.grid.col for p in members) + 1
        min_row = min(p.grid.row for p in members) - 1
        max_row = max(p.grid.row for p in members) + 1
        regions[sg_id] = {
            (c, r)
            for c in range(min_col, max_col + 1)
            for r in range(min_row, max_row + 1)
        }
    return regions


def _foreign_sg_cells(
    edge: Edge,
    graph: Graph,
    sg_regions: dict[str, set[tuple[int, int]]],
) -> set[tuple[int, int]]:
    """Cells of subgraph boxes this edge should avoid routing through.

    A subgraph is off-limits unless one of the edge's endpoints lives in it
    (or in a subgraph nested inside/around it).
    """
    if not sg_regions:
        return set()

    allowed: set[str] = set()
    for endpoint, is_sg in (
        (edge.source, edge.source_is_subgraph),
        (edge.target, edge.target_is_subgraph),
    ):
        if is_sg:
            sg = graph.find_subgraph_by_id(endpoint)
            # The subgraph itself, its ancestors, and its descendants: the
            # borrowed attachment cell may sit inside a nested child box.
            stack = [sg] if sg else []
            while stack:
                cur = stack.pop()
                allowed.add(cur.id)
                stack.extend(cur.children)
            while sg:
                allowed.add(sg.id)
                sg = sg.parent
        else:
            sg = graph.find_subgraph_for_node(endpoint)
            while sg:
                allowed.add(sg.id)
                sg = sg.parent

    cells: set[tuple[int, int]] = set()
    for sg_id, region in sg_regions.items():
        if sg_id not in allowed:
            cells |= region
    return cells


def _get_attach_point(
    placement: NodePlacement,
    attach_dir: AttachDir,
) -> tuple[int, int]:
    """Get the grid coordinate of an attachment point on a node."""
    gc = placement.grid
    if attach_dir == AttachDir.TOP:
        return (gc.col, gc.row - 1)
    elif attach_dir == AttachDir.BOTTOM:
        return (gc.col, gc.row + 1)
    elif attach_dir == AttachDir.LEFT:
        return (gc.col - 1, gc.row)
    else:  # RIGHT
        return (gc.col + 1, gc.row)


def _determine_directions(
    src: NodePlacement,
    tgt: NodePlacement,
    direction: Direction,
) -> tuple[tuple[AttachDir, AttachDir], tuple[AttachDir, AttachDir]]:
    """Determine preferred and alternative start/end attachment directions."""
    sc, sr = src.grid.col, src.grid.row
    tc, tr = tgt.grid.col, tgt.grid.row

    if direction.is_horizontal:
        # Primary flow is left-to-right
        if tc > sc:
            preferred = (AttachDir.RIGHT, AttachDir.LEFT)
        elif tc < sc:
            # Back-edge: exit BOTTOM to separate from other back-edges entering TOP
            preferred = (AttachDir.BOTTOM, AttachDir.BOTTOM)
            return preferred, (AttachDir.BOTTOM, AttachDir.TOP)
        else:
            preferred = (AttachDir.BOTTOM, AttachDir.TOP) if tr > sr else (AttachDir.TOP, AttachDir.BOTTOM)

        # Alternative uses vertical
        if tr > sr:
            alt = (AttachDir.BOTTOM, AttachDir.TOP)
        elif tr < sr:
            alt = (AttachDir.TOP, AttachDir.BOTTOM)
        else:
            alt = preferred
    else:
        # Primary flow is top-to-bottom
        if tr > sr:
            preferred = (AttachDir.BOTTOM, AttachDir.TOP)
        elif tr < sr:
            # Back-edge: exit RIGHT to separate from other back-edges entering LEFT
            preferred = (AttachDir.RIGHT, AttachDir.RIGHT)
            return preferred, (AttachDir.RIGHT, AttachDir.LEFT)
        else:
            preferred = (AttachDir.RIGHT, AttachDir.LEFT) if tc > sc else (AttachDir.LEFT, AttachDir.RIGHT)

        # Alternative uses horizontal
        if tc > sc:
            alt = (AttachDir.RIGHT, AttachDir.LEFT)
        elif tc < sc:
            alt = (AttachDir.LEFT, AttachDir.RIGHT)
        else:
            alt = preferred

    return preferred, alt


def _route_edge(
    edge: Edge,
    src: NodePlacement,
    tgt: NodePlacement,
    layout: GridLayout,
    direction: Direction,
    soft_obstacles: set[tuple[int, int]],
) -> RoutedEdge:
    """Route a single edge between two nodes."""
    preferred, alt = _determine_directions(src, tgt, direction)

    # Try preferred path
    # Don't exclude source/target from obstacles — edges must not route
    # through node borders. The pathfinder allows start/end points natively.
    start_pref = _get_attach_point(src, preferred[0])
    end_pref = _get_attach_point(tgt, preferred[1])

    path_pref = find_path(
        start_pref[0], start_pref[1],
        end_pref[0], end_pref[1],
        lambda c, r: layout.is_free(c, r),
        soft_obstacles,
    )

    # Try alternative path
    start_alt = _get_attach_point(src, alt[0])
    end_alt = _get_attach_point(tgt, alt[1])

    path_alt = find_path(
        start_alt[0], start_alt[1],
        end_alt[0], end_alt[1],
        lambda c, r: layout.is_free(c, r),
        soft_obstacles,
    )

    # Pick path: prefer the flow-aligned direction unless the alternative
    # is significantly shorter.  A small bias keeps edges exiting in the
    # natural flow direction (BOTTOM for TD, RIGHT for LR) which avoids
    # tight corners next to node borders.
    _PREFER_BIAS = 3  # allow preferred path to be up to 3 cells longer
    if path_pref and path_alt:
        if len(path_pref) <= len(path_alt) + _PREFER_BIAS:
            path, start_dir, end_dir = path_pref, preferred[0], preferred[1]
        else:
            path, start_dir, end_dir = path_alt, alt[0], alt[1]
    elif path_pref:
        path, start_dir, end_dir = path_pref, preferred[0], preferred[1]
    elif path_alt:
        path, start_dir, end_dir = path_alt, alt[0], alt[1]
    else:
        # Fallback: direct line
        path = [start_pref, end_pref]
        start_dir, end_dir = preferred

    simplified = simplify_path(path)

    # Convert to drawing coordinates (center of each cell)
    draw_path = [layout.grid_to_draw_center(c, r) for c, r in simplified]

    # Track occupied cells
    occupied = set(path)

    return RoutedEdge(
        edge=edge,
        grid_path=simplified,
        draw_path=draw_path,
        start_dir=start_dir,
        end_dir=end_dir,
        label=edge.label,
        occupied_cells=occupied,
    )


def _route_self_edge(
    edge: Edge,
    src: NodePlacement,
    layout: GridLayout,
    direction: Direction,
) -> RoutedEdge:
    """Route a self-referencing edge (A --> A).

    Self-edge loops out from the top, goes right, comes back down to the right side.
    """
    gc = src.grid

    # Loop: top → above-right → right → back to top-right area
    # Grid path: exit top, go up, go right, go down, enter right side
    path = [
        (gc.col, gc.row - 1),      # top border of node
        (gc.col, gc.row - 2),      # one cell above
        (gc.col + 2, gc.row - 2),  # above and to the right
        (gc.col + 2, gc.row),      # right and level with center
        (gc.col + 1, gc.row),      # right border of node
    ]
    start_dir = AttachDir.TOP
    end_dir = AttachDir.RIGHT

    draw_path = [layout.grid_to_draw_center(c, r) for c, r in path]
    occupied = set(path)

    return RoutedEdge(
        edge=edge,
        grid_path=path,
        draw_path=draw_path,
        start_dir=start_dir,
        end_dir=end_dir,
        label=edge.label,
        occupied_cells=occupied,
    )
