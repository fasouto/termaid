"""Grid-based layout engine for flowchart diagrams.

Each node occupies a 3x3 block on a logical grid. The center cell (1,1)
is the node's content area. The surrounding 8 cells provide attachment
points for edges. Nodes are spaced with a stride of 4 grid units
(3 for the block + 1 gap).

Layout algorithm:
1. Identify root nodes (no incoming edges)
2. Assign layers (distance from root in flow direction)
3. Order nodes within layers to minimize crossings (barycenter heuristic)
4. Map grid coordinates to drawing coordinates based on column widths/row heights
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..graph.model import Direction, Graph, Subgraph


STRIDE = 4  # Grid distance between node centers

# Node sizing constants
MAX_LABEL_WIDTH = 20       # Characters before wrapping
MAX_NORMALIZED_WIDTH = 25  # Cap for per-layer column normalization
MAX_NORMALIZED_HEIGHT = 7  # Cap for per-layer row normalization

# Subgraph layout constants
SG_BORDER_PAD = 2    # Padding between content and subgraph border
SG_LABEL_HEIGHT = 2  # Space for subgraph label + border line
SG_GAP_PER_LEVEL = SG_BORDER_PAD + SG_LABEL_HEIGHT + 1  # Gap per nesting level


@dataclass
class GridCoord:
    col: int
    row: int

    def __hash__(self) -> int:
        return hash((self.col, self.row))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GridCoord):
            return self.col == other.col and self.row == other.row
        return NotImplemented


@dataclass
class NodePlacement:
    node_id: str
    grid: GridCoord
    # Drawing coordinates (characters), set after column/row sizing
    draw_x: int = 0
    draw_y: int = 0
    draw_width: int = 0
    draw_height: int = 0


@dataclass
class SubgraphBounds:
    subgraph: Subgraph
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass
class GridLayout:
    """Result of the layout process."""
    placements: dict[str, NodePlacement] = field(default_factory=dict)
    col_widths: dict[int, int] = field(default_factory=dict)
    row_heights: dict[int, int] = field(default_factory=dict)
    grid_occupied: dict[tuple[int, int], str] = field(default_factory=dict)
    canvas_width: int = 0
    canvas_height: int = 0
    subgraph_bounds: list[SubgraphBounds] = field(default_factory=list)
    offset_x: int = 0
    offset_y: int = 0

    def is_free(self, col: int, row: int, exclude: set[str] | None = None) -> bool:
        """Check if a grid cell is not occupied by any node's 3x3 block."""
        if col < 0 or row < 0:
            return False
        key = (col, row)
        if key not in self.grid_occupied:
            return True
        if exclude and self.grid_occupied[key] in exclude:
            return True
        return False

    def grid_to_draw(self, col: int, row: int) -> tuple[int, int]:
        """Convert grid coordinates to drawing (character) coordinates.
        Returns the top-left position of the cell."""
        x = sum(self.col_widths.get(c, 1) for c in range(col)) + self.offset_x
        y = sum(self.row_heights.get(r, 1) for r in range(row)) + self.offset_y
        return x, y

    def grid_to_draw_center(self, col: int, row: int) -> tuple[int, int]:
        """Convert grid coordinates to the center of the cell in drawing coords."""
        x = sum(self.col_widths.get(c, 1) for c in range(col)) + self.offset_x
        y = sum(self.row_heights.get(r, 1) for r in range(row)) + self.offset_y
        w = self.col_widths.get(col, 1)
        h = self.row_heights.get(row, 1)
        return x + w // 2, y + h // 2


def compute_layout(graph: Graph, padding_x: int = 4, padding_y: int = 2) -> GridLayout:
    """Compute the grid layout for a graph."""
    layout = GridLayout()
    direction = graph.direction.normalized()

    if not graph.node_order:
        return layout

    # Step 1: Assign layers via BFS from roots
    layers = _assign_layers(graph)

    # Step 2: Order nodes within layers (barycenter heuristic)
    layer_order = _order_layers(graph, layers)

    # Step 3: Place nodes on the grid
    _place_nodes(graph, layout, layer_order, direction)

    # Step 4: Compute column widths and row heights (with word wrapping)
    _compute_sizes(graph, layout, padding_x, padding_y)

    # Step 4b: Normalize sizes (per-layer, capped)
    _normalize_sizes(graph, layout)

    # Step 5: Expand gaps for subgraph borders and labels
    _expand_gaps_for_subgraphs(graph, layout, direction)

    # Step 6: Compute drawing coordinates
    _compute_draw_coords(layout)

    # Step 7: Compute subgraph bounds
    _compute_subgraph_bounds(graph, layout)

    # Step 8: Adjust for negative subgraph bounds
    _adjust_for_negative_bounds(layout)

    # Step 9: Compute canvas size
    max_x = 0
    max_y = 0
    for p in layout.placements.values():
        max_x = max(max_x, p.draw_x + p.draw_width)
        max_y = max(max_y, p.draw_y + p.draw_height)
    for sb in layout.subgraph_bounds:
        max_x = max(max_x, sb.x + sb.width)
        max_y = max(max_y, sb.y + sb.height)
    layout.canvas_width = max_x
    layout.canvas_height = max_y

    return layout


def _assign_layers(graph: Graph) -> dict[str, int]:
    """Assign each node to a layer based on longest path from a root.

    Back-edges (edges that would create cycles) are excluded from
    layer computation to prevent infinite loops and excessive layers.
    """
    layers: dict[str, int] = {}
    roots = graph.get_roots()

    # BFS to assign initial layers
    for root in roots:
        if root not in layers:
            layers[root] = 0

    # Detect tree edges via BFS (shortest-path discovery).
    # BFS ensures each node is discovered at the shallowest depth,
    # so edges like F→D (where D is also reachable from B at a
    # shallower level) are correctly treated as back/cross-edges.
    from collections import deque
    tree_edges: set[tuple[str, str]] = set()
    visited: set[str] = set()

    queue: deque[str] = deque()
    for root in roots:
        if root not in visited:
            visited.add(root)
            queue.append(root)

    while queue:
        node = queue.popleft()
        for child in graph.get_children(node):
            if child not in visited:
                visited.add(child)
                tree_edges.add((node, child))
                queue.append(child)

    # Also BFS from any unvisited nodes (disconnected components)
    for nid in graph.node_order:
        if nid not in visited:
            visited.add(nid)
            queue.append(nid)
            while queue:
                node = queue.popleft()
                for child in graph.get_children(node):
                    if child not in visited:
                        visited.add(child)
                        tree_edges.add((node, child))
                        queue.append(child)

    # Build edge min_length lookup
    edge_min_lengths: dict[tuple[str, str], int] = {}
    for e in graph.edges:
        key = (e.source, e.target)
        edge_min_lengths[key] = max(edge_min_lengths.get(key, 1), e.min_length)

    # Assign layers using only tree edges (no back-edges)
    changed = True
    max_iter = len(graph.node_order) * 2
    iteration = 0
    while changed and iteration < max_iter:
        changed = False
        iteration += 1
        for src, tgt in tree_edges:
            if src in layers:
                ml = edge_min_lengths.get((src, tgt), 1)
                new_layer = layers[src] + ml
                if tgt not in layers or layers[tgt] < new_layer:
                    layers[tgt] = new_layer
                    changed = True

    # Assign unplaced nodes to layer 0
    for nid in graph.node_order:
        if nid not in layers:
            layers[nid] = 0

    # Collapse orthogonal subgraph nodes to the same layer
    ortho_sets = _get_orthogonal_sg_nodes(graph)
    if ortho_sets:
        for sg_nodes in ortho_sets:
            present = [nid for nid in sg_nodes if nid in layers]
            if not present:
                continue
            min_layer = min(layers[nid] for nid in present)
            for nid in present:
                layers[nid] = min_layer

        # Recompute layers for non-ortho nodes from scratch so downstream
        # nodes (like F) get pulled up to the correct layer after collapse.
        all_ortho = set()
        for s in ortho_sets:
            all_ortho.update(s)

        # Remove non-ortho nodes and recompute from roots
        for nid in graph.node_order:
            if nid not in all_ortho:
                layers.pop(nid, None)
        for root in graph.get_roots():
            if root not in layers:
                layers[root] = 0

        changed = True
        max_iter = len(graph.node_order) * 2
        iteration = 0
        while changed and iteration < max_iter:
            changed = False
            iteration += 1
            for src, tgt in tree_edges:
                if src in layers:
                    ml = edge_min_lengths.get((src, tgt), 1)
                    new_layer = layers[src] + ml
                    if tgt in all_ortho:
                        continue
                    if tgt not in layers or layers[tgt] < new_layer:
                        layers[tgt] = new_layer
                        changed = True

        for nid in graph.node_order:
            if nid not in layers:
                layers[nid] = 0

    return layers


def _order_layers(graph: Graph, layers: dict[str, int]) -> list[list[str]]:
    """Order nodes within each layer using barycenter heuristic."""
    # Group nodes by layer
    max_layer = max(layers.values()) if layers else 0
    layer_lists: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for nid in graph.node_order:
        layer_lists[layers.get(nid, 0)].append(nid)

    # Barycenter ordering: position each node at the average position of its neighbors
    for _pass in range(3):  # A few passes usually suffice
        for layer_idx in range(1, len(layer_lists)):
            prev_positions = {nid: i for i, nid in enumerate(layer_lists[layer_idx - 1])}
            barycenters: dict[str, float] = {}
            for nid in layer_lists[layer_idx]:
                # Find positions of predecessors in previous layer
                pred_positions: list[int] = []
                for edge in graph.edges:
                    if edge.target == nid and edge.source in prev_positions:
                        pred_positions.append(prev_positions[edge.source])
                if pred_positions:
                    barycenters[nid] = sum(pred_positions) / len(pred_positions)
                else:
                    barycenters[nid] = float(layer_lists[layer_idx].index(nid))

            layer_lists[layer_idx].sort(key=lambda n: barycenters.get(n, 0))

    # Enforce topological order for orthogonal subgraph nodes in the same layer
    ortho_sets = _get_orthogonal_sg_nodes(graph)
    if ortho_sets:
        for layer in layer_lists:
            for sg_nodes in ortho_sets:
                in_layer = [n for n in layer if n in sg_nodes]
                if len(in_layer) <= 1:
                    continue
                # Build topological order from internal edges
                internal = set(in_layer)
                successors: dict[str, list[str]] = {n: [] for n in internal}
                in_degree: dict[str, int] = {n: 0 for n in internal}
                for edge in graph.edges:
                    if edge.source in internal and edge.target in internal:
                        successors[edge.source].append(edge.target)
                        in_degree[edge.target] += 1
                # Kahn's algorithm
                queue = [n for n in in_layer if in_degree[n] == 0]
                topo: list[str] = []
                while queue:
                    node = queue.pop(0)
                    topo.append(node)
                    for succ in successors[node]:
                        in_degree[succ] -= 1
                        if in_degree[succ] == 0:
                            queue.append(succ)
                # Replace in-layer positions: find positions of sg nodes, fill with topo order
                positions = [i for i, n in enumerate(layer) if n in internal]
                for idx, pos in enumerate(positions):
                    if idx < len(topo):
                        layer[pos] = topo[idx]

    return layer_lists


def _place_nodes(
    graph: Graph,
    layout: GridLayout,
    layer_order: list[list[str]],
    direction: Direction,
) -> None:
    """Place nodes on the grid based on layer assignments."""
    for layer_idx, nodes in enumerate(layer_order):
        for pos_idx, nid in enumerate(nodes):
            if direction.is_horizontal:
                col = layer_idx * STRIDE + 1  # +1 for border cell
                row = pos_idx * STRIDE + 1
            else:
                col = pos_idx * STRIDE + 1
                row = layer_idx * STRIDE + 1

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
        if len(current_line) + 1 + len(word) <= max_width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


def _normalize_sizes(graph: Graph, layout: GridLayout) -> None:
    """Normalize node dimensions within the same layer, capped at a maximum.

    Nodes at the same flow level (same layer) are normalized to the same
    perpendicular dimension so side-by-side nodes look consistent.
    """
    direction = graph.direction.normalized()

    # Group placements by layer
    layer_groups: dict[int, list[NodePlacement]] = {}
    for p in layout.placements.values():
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


def _compute_sizes(
    graph: Graph,
    layout: GridLayout,
    padding_x: int,
    padding_y: int,
) -> None:
    """Compute column widths and row heights based on node content."""
    for nid, placement in layout.placements.items():
        node = graph.nodes[nid]
        label = node.label
        lines = label.split("\\n") if "\\n" in label else [label]

        # Word-wrap lines that exceed max width
        wrapped_lines: list[str] = []
        for line in lines:
            if len(line) <= MAX_LABEL_WIDTH:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(_word_wrap(line, MAX_LABEL_WIDTH))

        # Update the node's label with wrapped text
        if len(wrapped_lines) > 1 and wrapped_lines != lines:
            node.label = "\\n".join(wrapped_lines)

        text_width = max(len(l) for l in wrapped_lines) if wrapped_lines else 0
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
            layout.col_widths[c] = 4  # gap columns
    for r in range(max_row + 2):
        if r not in layout.row_heights:
            layout.row_heights[r] = 3  # gap rows

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
        label_len = len(edge.label)

        src_p = layout.placements.get(edge.source)
        tgt_p = layout.placements.get(edge.target)
        if not src_p or not tgt_p:
            continue

        if is_horizontal:
            # Edges run horizontally — label needs gap column width
            c1 = min(src_p.grid.col, tgt_p.grid.col)
            c2 = max(src_p.grid.col, tgt_p.grid.col)
            # Gap cells are between the two node 3x3 blocks
            gap_start = c1 + 2
            gap_end = c2 - 2
            if gap_start > gap_end:
                continue
            # Need: gap_width + 1 >= label_len + 2  →  gap_width >= label_len + 1
            needed = label_len + 1
            # Distribute across first gap cell (simplest approach)
            cur = layout.col_widths.get(gap_start, 4)
            layout.col_widths[gap_start] = max(cur, needed)
        else:
            # Edges run vertically — label placed beside the line (x+1)
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
            src_col = src_p.grid.col
            gap_col = src_col + 2  # gap cell to the right of node
            if gap_col in layout.col_widths:
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


def _expand_gaps_for_subgraphs(
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

    # Edge margins are handled by _adjust_for_negative_bounds (top/left)
    # and canvas size computation (bottom/right)


def _compute_draw_coords(layout: GridLayout) -> None:
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


def _compute_subgraph_bounds(
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


def _adjust_for_negative_bounds(layout: GridLayout) -> None:
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


def _gather_all_nodes(sg: Subgraph, result: set[str]) -> None:
    """Recursively gather all node IDs from a subgraph and its children."""
    result.update(sg.node_ids)
    for child in sg.children:
        _gather_all_nodes(child, result)


def _get_orthogonal_sg_nodes(graph: Graph) -> list[set[str]]:
    """Find sets of node IDs in subgraphs whose direction is orthogonal to the graph's."""
    graph_vertical = graph.direction.normalized().is_vertical
    result: list[set[str]] = []

    def _walk(subs: list[Subgraph]) -> None:
        for sg in subs:
            if sg.direction is not None:
                sg_vertical = sg.direction.normalized().is_vertical
                if sg_vertical != graph_vertical:
                    result.append(set(sg.node_ids))
            _walk(sg.children)

    _walk(graph.subgraphs)
    return result
