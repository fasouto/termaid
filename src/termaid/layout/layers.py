"""Layer assignment and ordering for the layout engine.

Assigns each node to a layer (depth from root) and orders nodes within
each layer to minimize edge crossings using a barycenter heuristic.
"""
from __future__ import annotations

from collections import Counter, deque
from typing import NamedTuple

from ..graph.model import Edge, Graph, Subgraph
from .grid import STRIDE, GridLayout


def expand_subgraph_edges(graph: Graph) -> list[Edge]:
    """Create virtual node-to-node edges for edges with subgraph endpoints.

    An edge like ``A --> B`` where A and B are subgraphs constrains every
    node of B to a layer below every node of A. Layer assignment only
    understands node-to-node edges, so expand each subgraph endpoint into
    its member nodes (recursively) and emit one virtual edge per pair.
    The virtual edges are used for layer assignment only and never drawn.
    """
    def _members(sg: Subgraph, result: set[str]) -> None:
        result.update(sg.node_ids)
        for child in sg.children:
            _members(child, result)

    virtual: list[Edge] = []
    for e in graph.edges:
        if not (e.source_is_subgraph or e.target_is_subgraph):
            continue
        sources: set[str] = set()
        targets: set[str] = set()
        for endpoint, is_sg, bucket in (
            (e.source, e.source_is_subgraph, sources),
            (e.target, e.target_is_subgraph, targets),
        ):
            if is_sg:
                sg = graph.find_subgraph_by_id(endpoint)
                if sg:
                    _members(sg, bucket)
            else:
                bucket.add(endpoint)
        if not sources or not targets or sources & targets:
            # Empty subgraph, self-edge, or nested endpoints: the
            # constraint is unsatisfiable, so skip it.
            continue
        order = {nid: i for i, nid in enumerate(graph.node_order)}
        for s in sorted(sources, key=lambda n: order.get(n, 0)):
            for t in sorted(targets, key=lambda n: order.get(n, 0)):
                virtual.append(Edge(source=s, target=t, min_length=e.min_length))
    return virtual


def assign_layers(graph: Graph, drawn: list[Edge] | None = None) -> dict[str, int]:
    """Assign each node to a layer based on longest path from a root.

    Back-edges (edges that would create cycles) are excluded from
    layer computation to prevent infinite loops and excessive layers.
    ``drawn`` are the edges that will be drawn, when ``graph.edges`` also
    holds edges used only to rank nodes; it defaults to all of them.
    """
    edge_min_lengths: dict[tuple[str, str], int] = {}
    for e in graph.edges:
        key = (e.source, e.target)
        edge_min_lengths[key] = max(edge_min_lengths.get(key, 1), e.min_length)

    # Longest path over the edges that close no cycle, as Mermaid ranks
    # nodes: a node reached by a short and a long path sits below the long
    # one, so its edges all point down the flow. Edges in definition order,
    # so which edge of a cycle turns back does not depend on hash order.
    forward = _without_back_edges(
        graph.node_order, [e for e in graph.edges if not e.is_self_reference],
    )
    links = list(dict.fromkeys((e.source, e.target) for e in forward))
    layers = _relax(graph, links, edge_min_lengths)

    # In a dense graph longest paths stretch many edges across several
    # layers, and each layer gap an edge crosses needs a lane of its own, so
    # the drawing gets much taller and slower to route. There the
    # breadth-first tree is kept, which ranks each node by its shortest
    # path from a root. Decided per connected part, so that many small
    # parts do not add up to one dense graph.
    tree = _bfs_tree_links(graph)
    tree_layers = _relax(graph, tree, edge_min_lengths)
    dense = _dense_parts(graph, graph.edges if drawn is None else drawn, layers, tree_layers)
    if dense:
        layers = {nid: tree_layers[nid] if nid in dense else layer for nid, layer in layers.items()}
        links = [l for l in links if l[0] not in dense] + [l for l in tree if l[0] in dense]
    has_parent = {tgt for _, tgt in links}

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
        for nid in graph.node_order:
            if nid not in has_parent:
                layers.setdefault(nid, 0)

        changed = True
        max_iter = len(graph.node_order) * 2
        iteration = 0
        while changed and iteration < max_iter:
            changed = False
            iteration += 1
            for src, tgt in links:
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


# Longest-path layering is kept for a connected part unless its drawn edges
# cross more than this many more layer gaps in all than with the
# breadth-first tree, and more than three for every four of its edges.
# Measured: at most 5 more in the test fixtures; 2 for every 3 or 4 edges
# in a flow of if/else merges, 0.72 per edge with ifs nested two deep; at
# least 0.78 per edge (45 over 58) in random graphs of 40 nodes and 60 edges.
_MAX_EXTRA_SPAN = 16


def _dense_parts(
    graph: Graph, drawn: list[Edge], layers: dict[str, int], tree_layers: dict[str, int],
) -> set[str]:
    """The nodes of each connected part whose longest-path layers stretch
    its edges too far, as ``_MAX_EXTRA_SPAN`` sets out."""
    part = {nid: nid for nid in layers}

    def find(nid: str) -> str:
        while part[nid] != nid:
            part[nid] = part[part[nid]]
            nid = part[nid]
        return nid

    for e in graph.edges:
        if e.source in part and e.target in part:
            part[find(e.source)] = find(e.target)
    extra: Counter[str] = Counter()
    edges: Counter[str] = Counter()
    for e in drawn:
        if e.source in part and e.target in part and e.source in tree_layers and e.target in tree_layers:
            root = find(e.source)
            extra[root] += abs(layers[e.target] - layers[e.source]) - abs(tree_layers[e.target] - tree_layers[e.source])
            edges[root] += 1
    dense = {root for root, n in extra.items() if n > _MAX_EXTRA_SPAN and 4 * n > 3 * edges[root]}
    return {nid for nid in part if find(nid) in dense} if dense else set()


def _relax(
    graph: Graph, links: list[tuple[str, str]], min_lengths: dict[tuple[str, str], int],
) -> dict[str, int]:
    """Push each link's target below its source until nothing moves. A
    node no link reaches sits on layer 0."""
    has_parent = {tgt for _, tgt in links}
    layers: dict[str, int] = {nid: 0 for nid in graph.node_order if nid not in has_parent}
    changed = True
    max_iter = len(graph.node_order) * 2
    iteration = 0
    while changed and iteration < max_iter:
        changed = False
        iteration += 1
        for src, tgt in links:
            if src in layers:
                new_layer = layers[src] + min_lengths.get((src, tgt), 1)
                if tgt not in layers or layers[tgt] < new_layer:
                    layers[tgt] = new_layer
                    changed = True
    for nid in graph.node_order:
        layers.setdefault(nid, 0)
    return layers


def _bfs_tree_links(graph: Graph) -> list[tuple[str, str]]:
    """The edges that first reach each node, breadth first from all the
    roots at once and then from each node not yet reached."""
    children: dict[str, list[str]] = {}
    for e in graph.edges:
        if e.source != e.target:
            kids = children.setdefault(e.source, [])
            if e.target not in kids:
                kids.append(e.target)
    tree: list[tuple[str, str]] = []
    visited: set[str] = set()

    def walk(starts: list[str]) -> None:
        visited.update(starts)
        queue = deque(starts)
        while queue:
            node = queue.popleft()
            for child in children.get(node, ()):
                if child not in visited:
                    visited.add(child)
                    tree.append((node, child))
                    queue.append(child)

    walk(list(dict.fromkeys(graph.get_roots())))
    for nid in graph.node_order:
        if nid not in visited:
            walk([nid])
    return tree


def _without_back_edges(nodes: list[str], edges: list[Edge]) -> list[Edge]:
    """Drop the edges that close a cycle (DFS in definition order).

    Longest-path layering over a cycle grows the layers on every pass until
    the pass limit, which stretches the subgraph and reverses its order.
    """
    succs: dict[str, list[Edge]] = {n: [] for n in nodes}
    for e in edges:
        succs.setdefault(e.source, []).append(e)
    state: dict[str, int] = {}  # 1 = on the DFS stack, 2 = done
    back: set[int] = set()

    targets = {e.target for e in edges}
    for root in [n for n in nodes if n not in targets] + nodes:
        if root in state:
            continue
        # An explicit stack, not recursion: a chain of a thousand nodes
        # would pass Python's recursion limit.
        state[root] = 1
        stack = [(root, iter(succs.get(root, [])))]
        while stack:
            node, outgoing = stack[-1]
            for e in outgoing:
                if state.get(e.target) == 1:
                    back.add(id(e))
                elif e.target not in state:
                    state[e.target] = 1
                    stack.append((e.target, iter(succs.get(e.target, []))))
                    break
            else:
                state[node] = 2
                stack.pop()
    return [e for e in edges if id(e) not in back]


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

    # Check for overlapping ranges between different subgraphs.
    # Declaration order, so sibling subgraphs stack the way they were written.
    sg_ids: list[str] = []

    def _declared(subs: list[Subgraph]) -> None:
        for sg in subs:
            if sg.id in sg_ranges:
                sg_ids.append(sg.id)
            _declared(sg.children)

    _declared(graph.subgraphs)
    has_overlap = _passes_through(graph, layers, node_sg, sg_ranges)
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

    # Build subgraph DAG from cross-boundary edges. Edges both ways between
    # subgraphs make a cycle; dropping its back edges still stacks them,
    # where giving up would leave their boxes on top of each other.
    # Lists, not sets: the topological order below must not depend on hash
    # order or sibling subgraphs would swap places between runs.
    sg_succs: dict[str, list[str]] = {sid: [] for sid in sg_ids}
    sg_in_deg: dict[str, int] = {sid: 0 for sid in sg_ids}
    sg_edges = [
        Edge(source=node_sg[e.source], target=node_sg[e.target])
        for e in graph.edges
        if node_sg.get(e.source) and node_sg.get(e.target)
        and node_sg[e.source] != node_sg[e.target]
    ]
    for e in _without_back_edges(sg_ids, sg_edges):
        if e.target not in sg_succs[e.source]:
            sg_succs[e.source].append(e.target)
            sg_in_deg[e.target] += 1

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

    # Compute internal layers per subgraph using only internal edges
    sg_internal: dict[str, dict[str, int]] = {}
    sg_sizes: dict[str, int] = {}
    for sg_id in topo:
        sg_nodes = [nid for nid in graph.node_order if node_sg.get(nid) == sg_id]
        sg_member = set(sg_nodes)
        int_edges = [e for e in graph.edges
                     if e.source in sg_member and e.target in sg_member
                     and not e.is_self_reference]
        int_edges = _without_back_edges(sg_nodes, int_edges)

        # Internal roots: nodes with no incoming internal edge
        int_targets = {e.target for e in int_edges}
        int_roots = [nid for nid in sg_nodes if nid not in int_targets]
        if not int_roots:
            int_roots = sg_nodes[:1]

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


def _passes_through(
    graph: Graph, layers: dict[str, int], node_sg: dict[str, str],
    sg_ranges: dict[str, tuple[int, int]],
) -> bool:
    """Whether a path leaves a subgraph and comes back through a node
    outside it, with that node inside the subgraph's layers. Stacked from
    the subgraph's own edges instead, the members lie side by side and
    the outside node follows them."""
    succs: dict[str, list[str]] = {}
    preds: dict[str, list[str]] = {}
    for e in graph.edges:
        succs.setdefault(e.source, []).append(e.target)
        preds.setdefault(e.target, []).append(e.source)

    def reach(start: set[str], step: dict[str, list[str]]) -> set[str]:
        seen = set(start)
        todo = list(start)
        while todo:
            for n in step.get(todo.pop(), ()):
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
        return seen

    for sg_id, (lo, hi) in sg_ranges.items():
        inside = {
            nid for nid, layer in layers.items()
            if lo < layer < hi and nid not in node_sg
        }
        if not inside:
            continue
        members = {nid for nid, s in node_sg.items() if s == sg_id}
        if inside & reach(members, succs) & reach(members, preds):
            return True
    return False


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

    # Enforce topological order for orthogonal subgraph nodes in the same
    # layer, reversed for a subgraph that runs RL or BT.
    ortho_sets = _orthogonal_subgraphs(graph)
    if ortho_sets:
        for layer in layer_lists:
            for sg_nodes, backward in ortho_sets:
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
                # Replace in-layer positions: find positions of sg nodes, fill with topo order.
                # A cycle leaves topo incomplete; rewriting then duplicates
                # some nodes and drops others, so keep the original order.
                positions = [i for i, n in enumerate(layer) if n in internal]
                if len(topo) != len(positions):
                    topo = in_layer
                if backward:
                    topo = topo[::-1]
                for idx, pos in enumerate(positions):
                    layer[pos] = topo[idx]

    if graph.subgraphs:
        layer_lists = [_group_subgraph_members(graph, layer) for layer in layer_lists]
    return layer_lists


def _group_subgraph_members(graph: Graph, layer: list[str]) -> list[str]:
    """Reorder a layer so each subgraph's members in it sit together.

    A box is drawn around all its members, so a node of the layer between
    two of them would be drawn inside it. Each subgraph, and each nested
    one within it, moves as a block to the mean position of its members,
    and a node outside it goes before or after the block, whichever side
    it was nearer. An order that already keeps every block together is
    left as it is.
    """
    position = {nid: i for i, nid in enumerate(layer)}
    chains: dict[str, list[str]] = {}
    for nid in layer:
        chain: list[str] = []
        sg = graph.find_subgraph_for_node(nid)
        while sg:
            chain.append(sg.id)
            sg = sg.parent
        chains[nid] = chain[::-1]

    def arrange(nodes: list[str], depth: int) -> list[str]:
        items: list[str | list[str]] = []
        blocks: dict[str, list[str]] = {}
        for nid in nodes:
            chain = chains[nid]
            if len(chain) <= depth:
                items.append(nid)
            elif chain[depth] in blocks:
                blocks[chain[depth]].append(nid)
            else:
                blocks[chain[depth]] = [nid]
                items.append(blocks[chain[depth]])

        def mean_position(item: str | list[str]) -> float:
            if isinstance(item, str):
                return position[item]
            return sum(position[n] for n in item) / len(item)

        result: list[str] = []
        for item in sorted(items, key=mean_position):
            if isinstance(item, str):
                result.append(item)
            else:
                result.extend(arrange(item, depth + 1))
        return result

    return arrange(layer, 0)


class BusKey(NamedTuple):
    """Names one bus: the node its edges share, which end that is, and how
    its edges look where they meet that node."""
    fan_in: bool
    hub: str
    look: tuple = ()


def bus_edges(graph: Graph) -> dict[BusKey, list[int]]:
    """Groups of unlabelled edges drawn as one shared line.

    A fan-out joins the edges of one source whose targets have no other
    incoming edge. A fan-in joins the edges into one target whose sources
    have no other outgoing edge. Either joins only edges that look alike
    where they meet the shared node, so a dotted and a solid edge never
    share a line.
    """
    in_degree = Counter(e.target for e in graph.edges)
    out_degree = Counter(e.source for e in graph.edges)
    groups: dict[BusKey, list[int]] = {}
    for i, e in enumerate(graph.edges):
        if e.label or e.is_self_reference:
            continue
        if in_degree[e.target] == 1:
            look = (e.style, e.has_arrow_start, e.arrow_type_start)
            groups.setdefault(BusKey(False, e.source, look), []).append(i)
        elif out_degree[e.source] == 1 and not (e.source_is_subgraph or e.target_is_subgraph):
            look = (e.style, e.has_arrow_end, e.arrow_type_end)
            groups.setdefault(BusKey(True, e.target, look), []).append(i)
    return {key: idxs for key, idxs in groups.items() if len(idxs) > 1}


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

    bus_of = {i: key for key, idxs in bus_edges(graph).items() for i in idxs}
    lanes_per_gap: dict[int, set[BusKey | int]] = {}
    for i, edge in enumerate(graph.edges):
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
            lane = bus_of[i] if i in bus_of and tgt_layer == src_layer + 1 else i
            lanes_per_gap.setdefault(gap_idx, set()).add(lane)

    return {gap: max(0, len(lanes) - 1) for gap, lanes in lanes_per_gap.items()}


def _get_orthogonal_sg_nodes(graph: Graph) -> list[set[str]]:
    """Find sets of node IDs in subgraphs whose direction is orthogonal to the graph's."""
    return [nodes for nodes, _ in _orthogonal_subgraphs(graph)]


def backward_subgraph_nodes(graph: Graph) -> list[set[str]]:
    """The members of each subgraph that runs against the graph's flow on
    the same axis, such as ``direction RL`` inside an LR graph.

    As in Mermaid, a subgraph with a node linked to the outside follows
    the graph's direction instead.
    """
    vertical = graph.direction.normalized().is_vertical
    result: list[set[str]] = []

    def _walk(subs: list[Subgraph]) -> None:
        for sg in subs:
            d = sg.direction
            if d is not None and d.normalized().is_vertical == vertical and d.is_reversed != graph.direction.is_reversed:
                members = set(sg.node_ids)
                if not any((e.source in members) != (e.target in members) for e in graph.edges):
                    result.append(members)
            _walk(sg.children)

    _walk(graph.subgraphs)
    return result


def reverse_backward_subgraphs(graph: Graph, layers: dict[str, int]) -> dict[str, int]:
    """Turn the layers of each subgraph that runs against the flow end
    over end, so its first node sits where its last one did."""
    for members in backward_subgraph_nodes(graph):
        present = [n for n in members if n in layers]
        if len(present) < 2:
            continue
        lo = min(layers[n] for n in present)
        hi = max(layers[n] for n in present)
        for n in present:
            layers[n] = lo + hi - layers[n]
    return layers


def _orthogonal_subgraphs(graph: Graph) -> list[tuple[set[str], bool]]:
    """The node IDs of each subgraph laid out across the graph's flow, and
    whether it runs backward along that cross axis (RL or BT)."""
    graph_vertical = graph.direction.normalized().is_vertical
    result: list[tuple[set[str], bool]] = []

    def _walk(subs: list[Subgraph]) -> None:
        for sg in subs:
            if sg.direction is not None:
                sg_vertical = sg.direction.normalized().is_vertical
                if sg_vertical != graph_vertical:
                    result.append((set(sg.node_ids), sg.direction.is_reversed))
            _walk(sg.children)

    _walk(graph.subgraphs)
    return result
