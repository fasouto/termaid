"""Layer assignment and ordering for the layout engine.

Assigns each node to a layer (depth from root) and orders nodes within
each layer to minimize edge crossings using a barycenter heuristic.
"""
from __future__ import annotations

from collections import deque

from ..graph.model import Graph, Subgraph
from .grid import STRIDE, GridLayout


def assign_layers(graph: Graph) -> dict[str, int]:
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
    # so edges like F->D (where D is also reachable from B at a
    # shallower level) are correctly treated as back/cross-edges.
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


def separate_subgraph_layers(graph: Graph, layers: dict[str, int]) -> dict[str, int]:
    """Fix overlapping subgraph layer ranges.

    When cross-boundary edges cause nodes from different subgraphs to land
    on the same layer, the subgraph boxes overlap visually. This function
    detects the overlap and reassigns layers so each subgraph occupies a
    contiguous, non-overlapping range.

    Internal edges within each subgraph determine relative node positions.
    Cross-boundary edges determine the ordering between subgraphs.
    """
    if not graph.subgraphs:
        return layers

    # Build node -> innermost subgraph mapping
    node_sg: dict[str, str] = {}

    def _map_sg(subs: list[Subgraph]) -> None:
        for sg in subs:
            _map_sg(sg.children)
            for nid in sg.node_ids:
                node_sg[nid] = sg.id

    _map_sg(graph.subgraphs)

    # Compute layer range per subgraph
    sg_ranges: dict[str, tuple[int, int]] = {}
    for nid, layer in layers.items():
        sg_id = node_sg.get(nid)
        if sg_id is None:
            continue
        if sg_id not in sg_ranges:
            sg_ranges[sg_id] = (layer, layer)
        else:
            lo, hi = sg_ranges[sg_id]
            sg_ranges[sg_id] = (min(lo, layer), max(hi, layer))

    if len(sg_ranges) < 2:
        return layers

    # Check for overlapping ranges between different subgraphs
    sg_ids = list(sg_ranges.keys())
    has_overlap = False
    for i in range(len(sg_ids)):
        for j in range(i + 1, len(sg_ids)):
            r1 = sg_ranges[sg_ids[i]]
            r2 = sg_ranges[sg_ids[j]]
            if r1[0] <= r2[1] and r2[0] <= r1[1]:
                has_overlap = True
                break
        if has_overlap:
            break

    if not has_overlap:
        return layers

    # Build subgraph DAG from cross-boundary edges
    sg_succs: dict[str, set[str]] = {sid: set() for sid in sg_ids}
    sg_in_deg: dict[str, int] = {sid: 0 for sid in sg_ids}
    for e in graph.edges:
        s_sg = node_sg.get(e.source)
        t_sg = node_sg.get(e.target)
        if s_sg and t_sg and s_sg != t_sg and s_sg in sg_succs:
            if t_sg not in sg_succs[s_sg]:
                sg_succs[s_sg].add(t_sg)
                sg_in_deg[t_sg] += 1

    # Topological sort (Kahn's)
    queue_list = [sid for sid in sg_ids if sg_in_deg[sid] == 0]
    topo: list[str] = []
    while queue_list:
        node = queue_list.pop(0)
        topo.append(node)
        for succ in sg_succs[node]:
            sg_in_deg[succ] -= 1
            if sg_in_deg[succ] == 0:
                queue_list.append(succ)

    if len(topo) != len(sg_ids):
        return layers  # cycle in subgraph DAG, fall back

    # Compute internal layers per subgraph using only internal edges
    sg_internal: dict[str, dict[str, int]] = {}
    sg_sizes: dict[str, int] = {}
    for sg_id in topo:
        sg_nodes = {nid for nid, sid in node_sg.items() if sid == sg_id}
        int_edges = [e for e in graph.edges
                     if e.source in sg_nodes and e.target in sg_nodes
                     and not e.is_self_reference]

        # Internal roots: nodes with no incoming internal edge
        int_targets = {e.target for e in int_edges}
        int_roots = [nid for nid in sg_nodes if nid not in int_targets]
        if not int_roots:
            int_roots = list(sg_nodes)[:1]

        int_layers: dict[str, int] = {r: 0 for r in int_roots}
        changed = True
        for _ in range(len(sg_nodes) * 2 + 1):
            if not changed:
                break
            changed = False
            for e in int_edges:
                if e.source in int_layers:
                    new_layer = int_layers[e.source] + 1
                    if e.target not in int_layers or int_layers[e.target] < new_layer:
                        int_layers[e.target] = new_layer
                        changed = True

        for nid in sg_nodes:
            if nid not in int_layers:
                int_layers[nid] = 0

        sg_internal[sg_id] = int_layers
        sg_sizes[sg_id] = (max(int_layers.values()) + 1) if int_layers else 0

    # Compute absolute offsets by stacking subgraphs in topo order.
    non_sg_layers = [l for nid, l in layers.items() if nid not in node_sg]
    first_sg_min = sg_ranges[topo[0]][0] if topo else 0
    non_sg_above = [l for l in non_sg_layers if l < first_sg_min]
    offset = (max(non_sg_above) + 1) if non_sg_above else 0

    sg_offsets: dict[str, int] = {}
    for sg_id in topo:
        sg_offsets[sg_id] = offset
        offset += sg_sizes[sg_id]

    # Build new layer assignment
    new_layers = dict(layers)
    for sg_id, int_layers in sg_internal.items():
        for nid, rel in int_layers.items():
            new_layers[nid] = sg_offsets[sg_id] + rel

    # Re-assign non-subgraph nodes: use longest-path from their predecessors
    non_sg = [nid for nid in graph.node_order if nid not in node_sg]
    if non_sg:
        for nid in non_sg:
            best = -1
            for e in graph.edges:
                if e.target == nid and e.source in new_layers:
                    best = max(best, new_layers[e.source])
            if best >= 0:
                new_layers[nid] = best + 1

    return new_layers


def _count_crossings(graph: Graph, layer_lists: list[list[str]]) -> int:
    """Count the total number of edge crossings between adjacent layers."""
    total = 0
    for layer_idx in range(1, len(layer_lists)):
        prev_pos = {nid: i for i, nid in enumerate(layer_lists[layer_idx - 1])}
        cur_pos = {nid: i for i, nid in enumerate(layer_lists[layer_idx])}
        # Collect edges between these two layers
        edges_between: list[tuple[int, int]] = []
        for edge in graph.edges:
            if edge.source in prev_pos and edge.target in cur_pos:
                edges_between.append((prev_pos[edge.source], cur_pos[edge.target]))
        # Count crossings: two edges (u1,v1) and (u2,v2) cross iff
        # u1 < u2 and v1 > v2 (or vice versa)
        for i in range(len(edges_between)):
            for j in range(i + 1, len(edges_between)):
                u1, v1 = edges_between[i]
                u2, v2 = edges_between[j]
                if (u1 - u2) * (v1 - v2) < 0:
                    total += 1
    return total


def order_layers(graph: Graph, layers: dict[str, int]) -> list[list[str]]:
    """Order nodes within each layer using barycenter heuristic."""
    # Group nodes by layer
    max_layer = max(layers.values()) if layers else 0
    layer_lists: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for nid in graph.node_order:
        layer_lists[layers.get(nid, 0)].append(nid)

    # Barycenter ordering with improvement tracking
    best_crossings = _count_crossings(graph, layer_lists)
    best_ordering = [layer[:] for layer in layer_lists]
    no_improvement = 0

    for _pass in range(8):  # Max 8 passes
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

        crossings = _count_crossings(graph, layer_lists)
        if crossings < best_crossings:
            best_crossings = crossings
            best_ordering = [layer[:] for layer in layer_lists]
            no_improvement = 0
        else:
            no_improvement += 1

        if no_improvement >= 4 or best_crossings == 0:
            break

    layer_lists = best_ordering

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
                kahn_queue = [n for n in in_layer if in_degree[n] == 0]
                topo: list[str] = []
                while kahn_queue:
                    node = kahn_queue.pop(0)
                    topo.append(node)
                    for succ in successors[node]:
                        in_degree[succ] -= 1
                        if in_degree[succ] == 0:
                            kahn_queue.append(succ)
                # Replace in-layer positions: find positions of sg nodes, fill with topo order
                positions = [i for i, n in enumerate(layer) if n in internal]
                for idx, pos in enumerate(positions):
                    if idx < len(topo):
                        layer[pos] = topo[idx]

    return layer_lists


def compute_gap_expansions(
    graph: Graph, layer_order: list[list[str]],
) -> dict[int, int]:
    """Compute extra grid cells needed between adjacent layers for crossing edges.

    When edges between two layers connect nodes at different perpendicular
    positions, they need horizontal (TD) or vertical (LR) routing space in
    the gap. If multiple such edges exist, the default single gap cell is
    not enough and they overlap. This function counts how many extra grid
    cells to insert per gap so the pathfinder has room to separate them.

    Returns a dict mapping gap index (between layer i and i+1) to the
    number of extra grid cells to insert.
    """
    # Build node -> (layer, position) lookup
    node_layer: dict[str, int] = {}
    node_pos: dict[str, int] = {}
    for layer_idx, nodes in enumerate(layer_order):
        for pos_idx, nid in enumerate(nodes):
            node_layer[nid] = layer_idx
            node_pos[nid] = pos_idx

    # Count edges that need horizontal routing per gap
    diagonal_per_gap: dict[int, int] = {}
    for edge in graph.edges:
        if edge.is_self_reference:
            continue
        src_layer = node_layer.get(edge.source)
        tgt_layer = node_layer.get(edge.target)
        if src_layer is None or tgt_layer is None:
            continue
        src_p = node_pos.get(edge.source, 0)
        tgt_p = node_pos.get(edge.target, 0)
        if src_p == tgt_p:
            continue  # straight edge, no horizontal routing needed

        # Count this edge for each gap it crosses
        lo, hi = min(src_layer, tgt_layer), max(src_layer, tgt_layer)
        for gap_idx in range(lo, hi):
            diagonal_per_gap[gap_idx] = diagonal_per_gap.get(gap_idx, 0) + 1

    # Extra cells = max(0, n_diagonal - 1): one edge fits in the default
    # gap cell, each additional edge needs one more cell.
    return {gap: max(0, n - 1) for gap, n in diagonal_per_gap.items()}


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
