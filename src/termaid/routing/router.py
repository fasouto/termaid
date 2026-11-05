"""Edge routing orchestrator.

Determines start/end attachment points on nodes, runs A* pathfinding,
and handles direction selection (preferred vs alternative paths).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable

from ..graph.model import Direction, Edge, Graph
from ..layout.grid import (
    SG_BORDER_PAD, GridLayout, NodePlacement, SubgraphBounds, compute_layout,
)
from ..layout.layers import bus_edges
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
    # Cells where the preferred route would share an unrelated edge's line
    # if lines were only soft obstacles
    crowded: set[tuple[int, int]] = field(default_factory=set)


_MAX_GAP_ROUNDS = 3
_CROWDING_COST = 10.0
_OFF_BUS_COST = 0.5


@dataclass
class _BusCells:
    branches: set[tuple[int, int]] = field(default_factory=set)
    preferred: set[tuple[int, int]] = field(default_factory=set)


def layout_and_route(
    graph: Graph,
    padding_x: int,
    padding_y: int,
    gap: int,
    max_label_width: int | None,
) -> tuple[GridLayout, list[RoutedEdge]]:
    """Lay out the graph and route its edges.

    A layer gap holding a crowded cell gets one more grid cell, as long as
    that leaves fewer crowded routes.
    """
    extra: dict[int, int] = {}
    layout = compute_layout(graph, padding_x, padding_y, gap, max_label_width)
    routed = route_edges(graph, layout)
    for _ in range(_MAX_GAP_ROUNDS):
        crowded = _crowded_gaps(routed, layout, graph.direction.normalized())
        if not crowded:
            break
        grown = {g: extra.get(g, 0) + (g in crowded) for g in extra.keys() | crowded}
        next_layout = compute_layout(graph, padding_x, padding_y, gap, max_label_width, grown)
        next_routed = route_edges(graph, next_layout)
        if sum(bool(r.crowded) for r in next_routed) >= sum(bool(r.crowded) for r in routed):
            break
        extra, layout, routed = grown, next_layout, next_routed
    return layout, routed


def _crowded_gaps(
    routed: list[RoutedEdge], layout: GridLayout, direction: Direction,
) -> set[int]:
    """Indexes of the layer gaps that hold a crowded cell."""
    coords = layout.layer_coords
    gaps: set[int] = set()
    for re in routed:
        for col, row in re.crowded:
            flow = row if direction.is_vertical else col
            gaps.update(
                i for i in range(len(coords) - 1)
                if coords[i] + 1 < flow < coords[i + 1] - 1
            )
    return gaps


def route_edges(graph: Graph, layout: GridLayout) -> list[RoutedEdge]:
    """Route all edges in the graph."""
    direction = graph.direction.normalized()
    routed: list[RoutedEdge] = []
    vertical = direction.is_vertical
    buses = bus_edges(graph)
    on_bus = {i for idxs in buses.values() for i in idxs}
    spans = _bus_spans(graph, layout, buses, vertical)
    bus_cells: dict[str, _BusCells] = {}

    # Build subgraph bounds lookup
    sg_bounds: dict[str, SubgraphBounds] = {}
    for sb in layout.subgraph_bounds:
        sg_bounds[sb.subgraph.id] = sb

    # Grid regions of each subgraph box: edges that neither start nor end
    # in a subgraph should avoid routing through its box.
    sg_regions = _compute_sg_regions(layout, sg_bounds)
    facing_homes: list[tuple[RoutedEdge, set[str]]] = []

    endpoints = [_resolve_endpoints(edge, layout, sg_bounds) for edge in graph.edges]
    places = [_endpoint_places(edge, graph) for edge in graph.edges]
    ends = {
        i: _end_cells(src, tgt, direction)
        for i, (src, tgt) in enumerate(endpoints)
        if src is not None and tgt is not None and not graph.edges[i].is_self_reference
    }

    order = _routing_order(graph, layout, buses)
    for pos, i in enumerate(order):
        edge = graph.edges[i]
        src, tgt = endpoints[i]

        if src is None or tgt is None:
            continue

        if edge.is_self_reference and not edge.source_is_subgraph:
            re = _route_self_edge(edge, src, layout, direction)
            re.index = i
            routed.append(re)
            continue

        forbidden = _foreign_sg_cells(edge, graph, sg_regions)
        facing = _flow_facing_homes(edge, graph, src, tgt, sg_regions, direction)
        penalty = _side_exit_penalty(facing, sg_regions, direction)
        shared, crossings, blocked = _occupancy(
            [(r, _related(places[i], places[r.index])) for r in routed],
            [ends[j] for j in order[pos + 1:]
             if j in ends and not _related(places[i], places[j])],
        )
        bus = bus_cells.setdefault(edge.source, _BusCells()) if i in on_bus else _BusCells()
        re = _route_edge(
            edge, src, tgt, layout, direction, (shared - bus.branches) | forbidden,
            _prefer_cells(bus.preferred, penalty), crossings, blocked,
        )
        re.index = i
        routed.append(re)
        facing_homes.append((re, facing))
        bus.branches.update(re.occupied_cells)
        if i in on_bus and _misalignment(edge, layout, vertical):
            if not bus.preferred:
                bus.preferred.update(_bus_lane(re.grid_path, spans[edge.source], vertical))
            bus.preferred.update(re.occupied_cells)

    routed.sort(key=lambda re: re.index)
    _step_off_four_way_splits(routed, layout, vertical)
    _fit_boxes_to_corridors(facing_homes, layout, sg_bounds, sg_regions, direction)

    # Snap subgraph-endpoint edges onto the subgraph border so they
    # attach to the box, not to the inner node used for routing.
    for re in routed:
        edge = re.edge
        if edge.source_is_subgraph and edge.source in sg_bounds:
            _clip_endpoint_to_box(re.draw_path, sg_bounds[edge.source], from_start=True)
        if edge.target_is_subgraph and edge.target in sg_bounds:
            _clip_endpoint_to_box(re.draw_path, sg_bounds[edge.target], from_start=False)

    # Post-process: spread edges that share the same target endpoint so
    # arrows don't overlap on the same cell.  Start points are NOT spread
    # because edges diverge naturally from a shared T-junction, and
    # spreading the start creates jog segments at the border that produce
    # ┼ artifacts when the jog crosses the node border characters.
    _spread_shared_endpoints(routed, layout, sg_bounds)

    return routed


_Places = tuple[frozenset[str], frozenset[str]]


def _endpoint_places(edge: Edge, graph: Graph) -> _Places:
    """The ids each end of an edge stands on. A subgraph end stands on its
    members too, since it is routed from one of their cells."""
    def place(endpoint: str, is_sg: bool) -> frozenset[str]:
        ids = {endpoint}
        stack = [graph.find_subgraph_by_id(endpoint)] if is_sg else []
        while stack:
            sg = stack.pop()
            if sg:
                ids.update(sg.node_ids)
                stack.extend(sg.children)
        return frozenset(ids)

    return (
        place(edge.source, edge.source_is_subgraph),
        place(edge.target, edge.target_is_subgraph),
    )


def _related(a: _Places, b: _Places) -> bool:
    """Edges that may share cells: a fan-out trunk, a fan-in trunk, or the
    two directions of one link."""
    (a_src, a_tgt), (b_src, b_tgt) = a, b
    return bool(a_src & b_src or a_tgt & b_tgt or (a_src & b_tgt and a_tgt & b_src))


def _end_cells(
    src: NodePlacement, tgt: NodePlacement, direction: Direction,
) -> list[tuple[tuple[int, int], bool]]:
    """The cells just outside an edge's preferred attachment points, each
    with whether the edge runs horizontally there."""
    (s_dir, t_dir), _ = _determine_directions(src, tgt, direction)
    cells = []
    for placement, attach in ((src, s_dir), (tgt, t_dir)):
        c, r = _get_attach_point(placement, attach)
        dc, dr = c - placement.grid.col, r - placement.grid.row
        cells.append(((c + dc, r + dr), dr == 0))
    return cells


def _occupancy(
    routed: list[tuple[RoutedEdge, bool]],
    pending_ends: list[list[tuple[tuple[int, int], bool]]],
) -> tuple[set[tuple[int, int]], dict[tuple[int, int], bool], set[tuple[int, int]]]:
    """Split the cells routed edges hold into what the next edge may share
    (those related to it), what it may only cross, and what it must avoid.

    An unrelated edge's straight run can be crossed; its corners and ends
    cannot. The cells where unrouted unrelated edges will leave or reach
    their nodes are held the same way, so this edge does not turn in them.
    """
    shared: set[tuple[int, int]] = set()
    crossings: dict[tuple[int, int], bool] = {}
    blocked: set[tuple[int, int]] = set()

    def hold(cell: tuple[int, int], horizontal: bool | None) -> None:
        if horizontal is None or crossings.get(cell, horizontal) != horizontal:
            blocked.add(cell)
        else:
            crossings[cell] = horizontal

    for other, related in routed:
        if related:
            shared.update(other.occupied_cells)
            continue
        for cell, horizontal in _cell_axes(other).items():
            hold(cell, horizontal)
    for ends in pending_ends:
        for cell, horizontal in ends:
            hold(cell, horizontal)
    for cell in blocked:
        crossings.pop(cell, None)
    return shared, crossings, blocked


def _cell_axes(re: RoutedEdge) -> dict[tuple[int, int], bool | None]:
    if re.edge.is_self_reference:
        return {cell: None for cell in re.occupied_cells}
    return _path_axes(re.grid_path)


def _path_axes(path: list[tuple[int, int]]) -> dict[tuple[int, int], bool | None]:
    """Each cell of a path: True where it runs straight horizontally, False
    straight vertically, None at its ends and corners."""
    cells = [path[0]]
    for (c0, r0), (c1, r1) in zip(path, path[1:]):
        dc, dr = (c1 > c0) - (c1 < c0), (r1 > r0) - (r1 < r0)
        while cells[-1] != (c1, r1):
            cells.append((cells[-1][0] + dc, cells[-1][1] + dr))
    axes: dict[tuple[int, int], bool | None] = {cells[0]: None, cells[-1]: None}
    for prev, cell, nxt in zip(cells, cells[1:], cells[2:]):
        straight = cell[0] - prev[0] == nxt[0] - cell[0] and cell[1] - prev[1] == nxt[1] - cell[1]
        axes[cell] = (prev[1] == cell[1]) if straight else None
    return axes


def _routing_order(graph: Graph, layout: GridLayout, buses: dict[str, list[int]]) -> list[int]:
    vertical = graph.direction.normalized().is_vertical

    def misalignment(i: int) -> int:
        return _misalignment(graph.edges[i], layout, vertical)

    order = list(range(len(graph.edges)))
    for indexes in buses.values():
        straightest_first = sorted(indexes, key=lambda i: (misalignment(i), i))
        for slot, i in zip(indexes, straightest_first):
            order[slot] = i
    return order


def _exits_by_cell(paths: list[list[tuple[int, int]]]) -> dict[tuple[int, int], set[tuple[int, int]]]:
    exits: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for path in paths:
        for (c0, r0), (c1, r1) in zip(path, path[1:]):
            dc, dr = (c1 > c0) - (c1 < c0), (r1 > r0) - (r1 < r0)
            c, r = c0, r0
            while (c, r) != (c1, r1):
                exits.setdefault((c, r), set()).add((dc, dr))
                c, r = c + dc, r + dr
                exits.setdefault((c, r), set()).add((-dc, -dr))
    return exits


def _step_off_four_way_splits(routed: list[RoutedEdge], layout: GridLayout, vertical: bool) -> None:
    by_source: dict[str, list[RoutedEdge]] = {}
    for re in routed:
        if not re.edge.is_self_reference:
            by_source.setdefault(re.edge.source, []).append(re)
    for lines in by_source.values():
        if len(lines) < 3:
            continue
        exits_per_line = [_exits_by_cell([re.grid_path]) for re in lines]
        for cell, exits in _exits_by_cell([re.grid_path for re in lines]).items():
            straight_through = sum(
                len(own.get(cell, ())) == 2 and _is_straight(own[cell]) for own in exits_per_line
            )
            is_crossing = straight_through >= 2
            if len(exits) == 4 and not is_crossing:
                x, y = layout.grid_to_draw_center(*cell)
                for re in lines:
                    if _step_aside(re.draw_path, x, y, vertical):
                        break


def _is_straight(exits: set[tuple[int, int]]) -> bool:
    (a, b), (c, d) = exits
    return (a, b) == (-c, -d)


def _step_aside(path: list[tuple[int, int]], x: int, y: int, vertical: bool) -> bool:
    for k, ((x0, y0), (x1, y1)) in enumerate(zip(path, path[1:])):
        through = (x0 == x1 == x and min(y0, y1) < y < max(y0, y1)) if vertical else (
            y0 == y1 == y and min(x0, x1) < x < max(x0, x1))
        if through:
            side = (x + 1, y) if vertical else (x, y + 1)
            end = (x1 + 1, y1) if vertical else (x1, y1 + 1)
            path[k + 1:k + 2] = [(x, y), side, end]
            return True
    return False


def _misalignment(edge: Edge, layout: GridLayout, vertical: bool) -> int:
    src = layout.placements.get(edge.source)
    tgt = layout.placements.get(edge.target)
    if not src or not tgt:
        return 0
    if vertical:
        return abs(tgt.grid.col - src.grid.col)
    return abs(tgt.grid.row - src.grid.row)


def _bus_spans(
    graph: Graph, layout: GridLayout, buses: dict[str, list[int]], vertical: bool,
) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for source, indexes in buses.items():
        src = layout.placements.get(source)
        if not src:
            continue
        a = src.grid.col if vertical else src.grid.row
        lo, hi = a, a
        for i in indexes:
            tgt = layout.placements.get(graph.edges[i].target)
            if tgt:
                b = tgt.grid.col if vertical else tgt.grid.row
                lo, hi = min(lo, b), max(hi, b)
        spans[source] = (lo, hi)
    return spans


def _bus_lane(path: list[tuple[int, int]], span: tuple[int, int], vertical: bool) -> set[tuple[int, int]]:
    for (c1, r1), (c2, r2) in zip(path, path[1:]):
        if vertical and r1 == r2 and c1 != c2:
            return {(c, r1) for c in range(span[0], span[1] + 1)}
        if not vertical and c1 == c2 and r1 != r2:
            return {(c1, r) for r in range(span[0], span[1] + 1)}
    return set()


def _prefer_cells(
    cells: set[tuple[int, int]], penalty: Callable[[int, int], float] | None,
) -> Callable[[int, int], float] | None:
    if not cells:
        return penalty

    def cost(c: int, r: int) -> float:
        return (penalty(c, r) if penalty else 0.0) + _OFF_BUS_COST * ((c, r) not in cells)
    return cost


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
) -> dict[str, tuple[int, int, int, int]]:
    """Grid extent (min_col, max_col, min_row, max_row) of each subgraph box:
    its member blocks plus their border channels."""
    regions: dict[str, tuple[int, int, int, int]] = {}
    for sg_id, sb in sg_bounds.items():
        members = _sg_member_placements(sb, layout)
        if not members:
            continue
        regions[sg_id] = (
            min(p.grid.col for p in members) - 1,
            max(p.grid.col for p in members) + 1,
            min(p.grid.row for p in members) - 1,
            max(p.grid.row for p in members) + 1,
        )
    return regions


def _home_chain(endpoint: str, is_sg: bool, graph: Graph) -> list[str]:
    """The subgraph an endpoint lives in, then its ancestors."""
    sg = graph.find_subgraph_by_id(endpoint) if is_sg else graph.find_subgraph_for_node(endpoint)
    chain: list[str] = []
    while sg:
        chain.append(sg.id)
        sg = sg.parent
    return chain


def _flow_facing_homes(
    edge: Edge,
    graph: Graph,
    src: NodePlacement,
    tgt: NodePlacement,
    sg_regions: dict[str, tuple[int, int, int, int]],
    direction: Direction,
) -> set[str]:
    """Home subgraphs the edge has no reason to leave through the side.

    That is every home subgraph, except one whose layers the far endpoint
    shares from outside the box: an edge to a node beside the box has to
    cross its side border.
    """
    src_chain = _home_chain(edge.source, edge.source_is_subgraph, graph)
    tgt_chain = _home_chain(edge.target, edge.target_is_subgraph, graph)
    facing: set[str] = set()
    for chain, other_chain, other in ((src_chain, tgt_chain, tgt), (tgt_chain, src_chain, src)):
        other_flow = other.grid.row if direction.is_vertical else other.grid.col
        for sg_id in chain:
            if sg_id not in sg_regions:
                continue
            c0, c1, r0, r1 = sg_regions[sg_id]
            f0, f1 = (r0, r1) if direction.is_vertical else (c0, c1)
            if sg_id in other_chain or not f0 <= other_flow <= f1:
                facing.add(sg_id)
    return facing


def _foreign_sg_cells(
    edge: Edge,
    graph: Graph,
    sg_regions: dict[str, tuple[int, int, int, int]],
) -> set[tuple[int, int]]:
    """Cells of subgraph boxes this edge should avoid routing through.

    A subgraph is off-limits unless one of the edge's endpoints lives in it
    (or in a subgraph nested inside/around it).
    """
    if not sg_regions:
        return set()

    allowed = set(
        _home_chain(edge.source, edge.source_is_subgraph, graph)
        + _home_chain(edge.target, edge.target_is_subgraph, graph)
    )
    for endpoint, is_sg in (
        (edge.source, edge.source_is_subgraph),
        (edge.target, edge.target_is_subgraph),
    ):
        if is_sg:
            # Descendants too: the borrowed attachment cell may sit inside
            # a nested child box.
            stack = [graph.find_subgraph_by_id(endpoint)]
            while stack:
                cur = stack.pop()
                if cur:
                    allowed.add(cur.id)
                    stack.extend(cur.children)

    cells: set[tuple[int, int]] = set()
    for sg_id, (c0, c1, r0, r1) in sg_regions.items():
        if sg_id not in allowed:
            cells.update((c, r) for c in range(c0, c1 + 1) for r in range(r0, r1 + 1))
    return cells


def _side_exit_penalty(
    homes: set[str],
    sg_regions: dict[str, tuple[int, int, int, int]],
    direction: Direction,
) -> Callable[[int, int], float] | None:
    """Cost of a cell beside one of the edge's home subgraphs.

    Leaving a subgraph through its side means running alongside it outside
    the box. Charging those cells makes the edge cross the border on the
    flow-facing side and go around sibling nodes in the gap column next to
    them, which ``_fit_boxes_to_corridors`` then keeps inside the box.
    """
    bands = []
    for sg_id in homes:
        c0, c1, r0, r1 = sg_regions[sg_id]
        if direction.is_vertical:
            bands.append((r0, r1, c0 - 1, c1 + 1))
        else:
            bands.append((c0, c1, r0 - 1, r1 + 1))
    if not bands:
        return None

    def penalty(col: int, row: int) -> float:
        flow, cross = (row, col) if direction.is_vertical else (col, row)
        return 2.0 * sum(
            1 for f0, f1, x0, x1 in bands
            if f0 <= flow <= f1 and not x0 <= cross <= x1
        )
    return penalty


def _fit_boxes_to_corridors(
    facing_homes: list[tuple[RoutedEdge, set[str]]],
    layout: GridLayout,
    sg_bounds: dict[str, SubgraphBounds],
    sg_regions: dict[str, tuple[int, int, int, int]],
    direction: Direction,
) -> None:
    """Widen a subgraph box over the gap column beside its nodes when one
    of its edges runs there.

    Boxes hug their nodes, but the gap column next to the outermost nodes
    is the only corridor an edge has for going around them, and its center
    lies past the border padding.
    """
    vertical = direction.is_vertical
    for re, facing in facing_homes:
        for sg_id in facing:
            c0, c1, r0, r1 = sg_regions[sg_id]
            f0, f1, x0, x1 = (r0, r1, c0, c1) if vertical else (c0, c1, r0, r1)
            step = (0, 1) if vertical else (1, 0)
            beside = {
                (c, r) for c, r in re.occupied_cells
                if f0 <= (r if vertical else c) <= f1
                and (c if vertical else r) in (x0 - 1, x1 + 1)
            }
            # Only a run along the side counts; a single cell is the edge
            # crossing the corridor on its way into or out of the box.
            corridor = [
                layout.grid_to_draw_center(c, r)
                for c, r in sorted(beside)
                if (c + step[0], r + step[1]) in beside
                or (c - step[0], r - step[1]) in beside
            ]
            if corridor:
                _grow_box(sg_bounds[sg_id], corridor, layout, vertical)

    # Parents come after their children in subgraph_bounds.
    for sb in layout.subgraph_bounds:
        for child in sb.subgraph.children:
            cb = sg_bounds.get(child.id)
            if cb:
                corners = [(cb.x, cb.y), (cb.x + cb.width - 1, cb.y + cb.height - 1)]
                _grow_box(sb, corners, layout, vertical)


def _grow_box(
    sb: SubgraphBounds,
    points: list[tuple[int, int]],
    layout: GridLayout,
    vertical: bool,
) -> None:
    """Grow the box across the flow axis to keep SG_BORDER_PAD around points."""
    if vertical:
        lo = min(sb.x, min(x for x, _ in points) - SG_BORDER_PAD)
        hi = max(sb.x + sb.width - 1, max(x for x, _ in points) + SG_BORDER_PAD)
        sb.x, sb.width = lo, hi - lo + 1
        layout.canvas_width = max(layout.canvas_width, hi + 1)
    else:
        lo = min(sb.y, min(y for _, y in points) - SG_BORDER_PAD)
        hi = max(sb.y + sb.height - 1, max(y for _, y in points) + SG_BORDER_PAD)
        sb.y, sb.height = lo, hi - lo + 1
        layout.canvas_height = max(layout.canvas_height, hi + 1)


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
    penalty: Callable[[int, int], float] | None,
    crossings: dict[tuple[int, int], bool],
    blocked: set[tuple[int, int]],
) -> RoutedEdge:
    """Route a single edge between two nodes.

    The route keeps off ``blocked`` cells and passes ``crossings`` only
    perpendicularly. When neither attachment allows that, it takes the
    path through the fewest such cells.
    """
    preferred, alt = _determine_directions(src, tgt, direction)

    # Try preferred path
    # Don't exclude source/target from obstacles — edges must not route
    # through node borders. The pathfinder allows start/end points natively.
    start_pref = _get_attach_point(src, preferred[0])
    end_pref = _get_attach_point(tgt, preferred[1])

    def clear(c: int, r: int) -> bool:
        return layout.is_free(c, r) and (c, r) not in blocked

    def crowding(c: int, r: int) -> float:
        held = (c, r) in blocked or (c, r) in crossings
        return (penalty(c, r) if penalty else 0.0) + _CROWDING_COST * held

    def search(start: tuple[int, int], end: tuple[int, int], strict: bool):
        if strict:
            return find_path(
                *start, *end, clear, soft_obstacles, penalty=penalty, crossings=crossings,
            )
        return find_path(*start, *end, layout.is_free, soft_obstacles, penalty=crowding)

    path_pref = search(start_pref, end_pref, strict=True)

    # Try alternative path
    start_alt = _get_attach_point(src, alt[0])
    end_alt = _get_attach_point(tgt, alt[1])

    path_alt = search(start_alt, end_alt, strict=True)

    # The preferred route as it would be if other lines were only soft
    # obstacles. Where it shares one, the gap there has no room to spare.
    ideal = find_path(
        *start_pref, *end_pref, layout.is_free,
        soft_obstacles | blocked | crossings.keys(), penalty=penalty,
    )
    crowded = {
        cell for cell, horizontal in (_path_axes(ideal) if ideal else {}).items()
        if cell in blocked or (cell in crossings and horizontal in (None, crossings[cell]))
    }

    if path_pref is None and path_alt is None:
        path_pref = search(start_pref, end_pref, strict=False)
        path_alt = search(start_alt, end_alt, strict=False)

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
        crowded=crowded,
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
