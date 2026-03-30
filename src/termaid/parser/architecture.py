"""Parser for Mermaid architecture diagrams.

Converts architecture-beta syntax into a Graph model so it can
be rendered using the existing flowchart renderer. Uses the L/R/T/B
direction hints on edges to position nodes on a 2D grid.

Syntax:
    architecture-beta
        group api(cloud)[API]
        service db(database)[Database] in api
        service server(server)[Server] in api
        db:R --> L:server
"""
from __future__ import annotations

import re

from ..graph.model import Direction, Edge, Graph, Node, Subgraph
from ..graph.shapes import NodeShape


# Map architecture icons to node shapes.
_ICON_SHAPES = {
    "cloud": NodeShape.RECTANGLE,
    "database": NodeShape.RECTANGLE,
    "disk": NodeShape.RECTANGLE,
    "server": NodeShape.RECTANGLE,
    "internet": NodeShape.RECTANGLE,
}

# Icon prefixes for labels
_ICON_PREFIX = {
    "cloud": "☁ ",
    "database": "🗄 ",
    "disk": "💾 ",
    "server": "🖥 ",
    "internet": "🌐 ",
}


def parse_architecture(text: str) -> Graph:
    """Parse an architecture-beta diagram into a Graph model."""
    lines = text.strip().splitlines()
    graph = Graph(direction=Direction.TB)

    if not lines:
        return graph

    groups: dict[str, Subgraph] = {}
    services: dict[str, str] = {}  # id -> parent group id
    edge_hints: list[tuple[str, str, str, str]] = []  # (src, src_dir, tgt, tgt_dir)
    all_node_ids: list[str] = []

    for line in lines[1:]:  # skip "architecture-beta" header
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue

        # Group: group id(icon)[label] [in parent]
        m = re.match(r'^group\s+(\w+)(?:\(([^)]*)\))?\[([^\]]*)\](?:\s+in\s+(\w+))?', stripped)
        if m:
            gid = m.group(1)
            label = m.group(3)
            parent_id = m.group(4)

            sg = Subgraph(id=gid, label=label)
            if parent_id and parent_id in groups:
                groups[parent_id].children.append(sg)
                sg.parent = groups[parent_id]
            else:
                graph.subgraphs.append(sg)
            groups[gid] = sg
            continue

        # Service: service id(icon)[label] [in group]
        m = re.match(r'^service\s+(\w+)(?:\(([^)]*)\))?\[([^\]]*)\](?:\s+in\s+(\w+))?', stripped)
        if m:
            sid = m.group(1)
            icon = m.group(2) or ""
            label = m.group(3)
            parent_id = m.group(4)

            prefix = _ICON_PREFIX.get(icon, "")
            shape = _ICON_SHAPES.get(icon, NodeShape.RECTANGLE)

            node = Node(id=sid, label=prefix + label, shape=shape)
            graph.add_node(node)
            all_node_ids.append(sid)

            if parent_id and parent_id in groups:
                groups[parent_id].node_ids.append(sid)
                services[sid] = parent_id
            continue

        # Junction: junction id [in group]
        m = re.match(r'^junction\s+(\w+)(?:\s+in\s+(\w+))?', stripped)
        if m:
            jid = m.group(1)
            parent_id = m.group(2)

            node = Node(id=jid, label="", shape=NodeShape.JUNCTION)
            graph.add_node(node)
            all_node_ids.append(jid)

            if parent_id and parent_id in groups:
                groups[parent_id].node_ids.append(jid)
            continue

        # Edge: id{group}?:DIR arrow--arrow DIR:id{group}?
        m = re.match(
            r'^(\w+)(?:\{(\w+)\})?:([LRTB])\s+'
            r'(<?)--(-?)(>?)\s+'
            r'([LRTB]):(\w+)(?:\{(\w+)\})?',
            stripped,
        )
        if m:
            src = m.group(1)
            src_dir = m.group(3)
            has_arrow_start = m.group(4) == "<"
            has_arrow_end = m.group(6) == ">"
            tgt_dir = m.group(7)
            tgt = m.group(8)

            edge = Edge(
                source=src,
                target=tgt,
                has_arrow_start=has_arrow_start,
                has_arrow_end=has_arrow_end,
            )
            graph.add_edge(edge)
            edge_hints.append((src, src_dir, tgt, tgt_dir))
            continue

        # Simpler edge: id --> id or id -- id
        m = re.match(r'^(\w+)\s*(<?)--(-?)(>?)\s*(\w+)', stripped)
        if m:
            src = m.group(1)
            has_arrow_start = m.group(2) == "<"
            has_arrow_end = m.group(4) == ">"
            tgt = m.group(5)

            edge = Edge(
                source=src,
                target=tgt,
                has_arrow_start=has_arrow_start,
                has_arrow_end=has_arrow_end,
            )
            graph.add_edge(edge)

    # Use direction hints to position nodes on a 2D grid.
    if edge_hints:
        positions = _compute_grid_positions(all_node_ids, edge_hints)

        # Eliminate junction nodes: replace with direct edges between neighbors.
        junction_ids = {nid for nid, n in graph.nodes.items() if n.shape == NodeShape.JUNCTION}
        if junction_ids:
            _eliminate_junctions(graph, junction_ids, edge_hints)
            # Remove junctions from positions and node lists
            for jid in junction_ids:
                positions.pop(jid, None)

        _apply_direction_and_positions(graph, positions)

    return graph


def _eliminate_junctions(
    graph: Graph,
    junction_ids: set[str],
    edge_hints: list[tuple[str, str, str, str]],
) -> None:
    """Remove junction nodes and connect their neighbors directly.

    Resolves junction chains first (junction -> junction), then for each
    junction, pairs neighbors on opposite sides (L-R or T-B).
    """
    _OPPOSITES = {"L": "R", "R": "L", "T": "B", "B": "T"}

    # Build neighbor map for each junction from edge hints.
    junc_neighbors: dict[str, list[tuple[str, str]]] = {jid: [] for jid in junction_ids}
    for src, src_dir, tgt, tgt_dir in edge_hints:
        if src in junction_ids:
            junc_neighbors[src].append((tgt, src_dir))
        if tgt in junction_ids:
            junc_neighbors[tgt].append((src, tgt_dir))

    # Resolve junction-to-junction links: trace through junction chains
    # to find the real (non-junction) endpoint and its effective side.
    def _resolve(nid: str, side: str, visited: set[str]) -> list[tuple[str, str]]:
        """Follow junction chains, returning (real_node, side) pairs."""
        if nid not in junction_ids:
            return [(nid, side)]
        if nid in visited:
            return []
        visited.add(nid)
        # This junction's exit side is opposite of the entry side
        exit_side = _OPPOSITES.get(side, side)
        results: list[tuple[str, str]] = []
        for neighbor, neighbor_side in junc_neighbors[nid]:
            if neighbor_side == exit_side:
                results.extend(_resolve(neighbor, _OPPOSITES.get(neighbor_side, neighbor_side), visited))
        # Also collect non-exit-side real neighbors for star connections
        if not results:
            for neighbor, neighbor_side in junc_neighbors[nid]:
                if neighbor not in junction_ids and neighbor not in visited:
                    results.append((neighbor, neighbor_side))
        return results

    # For each junction, pair its resolved real neighbors on opposite sides
    all_new_edges: set[tuple[str, str]] = set()

    for jid in junction_ids:
        # Collect real neighbors with their side on this junction
        real_neighbors: list[tuple[str, str]] = []
        for neighbor, side in junc_neighbors[jid]:
            resolved = _resolve(neighbor, _OPPOSITES.get(side, side), {jid})
            for rn, _ in resolved:
                real_neighbors.append((rn, side))

        # Pair on opposite sides
        paired: set[int] = set()
        for i, (n1, d1) in enumerate(real_neighbors):
            if i in paired:
                continue
            opp = _OPPOSITES.get(d1)
            for j, (n2, d2) in enumerate(real_neighbors):
                if j != i and j not in paired and d2 == opp:
                    edge_key = (min(n1, n2), max(n1, n2))
                    all_new_edges.add(edge_key)
                    paired.add(i)
                    paired.add(j)
                    break

    # Remove all edges involving junctions
    graph.edges = [e for e in graph.edges
                   if e.source not in junction_ids and e.target not in junction_ids]

    # Add new direct edges
    for src, tgt in all_new_edges:
        graph.add_edge(Edge(source=src, target=tgt))

    # Remove junction nodes
    for jid in junction_ids:
        graph.nodes.pop(jid, None)
        if jid in graph.node_order:
            graph.node_order.remove(jid)
        for sg in graph.subgraphs:
            if jid in sg.node_ids:
                sg.node_ids.remove(jid)


def _compute_grid_positions(
    node_ids: list[str],
    hints: list[tuple[str, str, str, str]],
) -> dict[str, tuple[int, int]]:
    """Compute (col, row) positions from direction hints.

    If src exits R and tgt enters L, tgt is to the right of src.
    If src exits B and tgt enters T, tgt is below src.
    """
    pos: dict[str, tuple[int, int]] = {}

    if not node_ids:
        return pos

    # Place first node at origin
    pos[node_ids[0]] = (0, 0)

    # Direction offsets: which direction does the TARGET move relative to SOURCE?
    # src:R -- L:tgt means tgt is RIGHT of src: col +1
    # src:B -- T:tgt means tgt is BELOW src: row +1
    # src:L -- R:tgt means tgt is LEFT of src: col -1
    # src:T -- B:tgt means tgt is ABOVE src: row -1
    _SRC_OFFSET = {
        "R": (1, 0),   # exit right = target is to the right
        "L": (-1, 0),  # exit left = target is to the left
        "B": (0, 1),   # exit bottom = target is below
        "T": (0, -1),  # exit top = target is above
    }

    # Multiple passes to resolve chains
    for _ in range(len(node_ids) + 1):
        changed = False
        for src, src_dir, tgt, tgt_dir in hints:
            if src in pos and tgt not in pos:
                sc, sr = pos[src]
                dc, dr = _SRC_OFFSET.get(src_dir, (1, 0))
                pos[tgt] = (sc + dc, sr + dr)
                changed = True
            elif tgt in pos and src not in pos:
                tc, tr = pos[tgt]
                dc, dr = _SRC_OFFSET.get(src_dir, (1, 0))
                pos[src] = (tc - dc, tr - dr)
                changed = True
        if not changed:
            break

    # Place any remaining nodes not reached by hints
    max_col = max((c for c, _ in pos.values()), default=0) + 1
    for nid in node_ids:
        if nid not in pos:
            pos[nid] = (max_col, 0)
            max_col += 1

    # Normalize to non-negative coordinates
    min_col = min(c for c, _ in pos.values())
    min_row = min(r for _, r in pos.values())
    return {nid: (c - min_col, r - min_row) for nid, (c, r) in pos.items()}


def _apply_direction_and_positions(
    graph: Graph,
    positions: dict[str, tuple[int, int]],
) -> None:
    """Set graph direction and grid_positions for the layout engine."""
    if not positions:
        return

    max_col = max(c for c, _ in positions.values())
    max_row = max(r for _, r in positions.values())

    # Pick direction based on grid shape
    if max_col >= max_row:
        graph.direction = Direction.LR
    else:
        graph.direction = Direction.TB

    graph.grid_positions = positions
