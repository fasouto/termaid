"""Layered layout and routing shared by class and ER diagrams.

Boxes sit in layers (rows for TB, columns for LR). Layers come from the
longest path through the links, so every link runs from one layer to a
later one: no link joins two boxes of the same layer, where it would have
to cross the boxes between them. A link that spans several layers passes
through a reserved slot in each layer it crosses. Inside the gap between
two layers each sideways jog gets its own track, and a label that cannot
ride on its own jog gets a label row (TB) or sits on the line into its box
(LR), with the layout widened when it would otherwise run into a line.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from ..utils import display_width

MARGIN = 2
_DUMMY = "\x00"


@dataclass
class Link:
    a: str                 # start end (class source, ER first entity)
    b: str                 # finish end
    a_above: bool = True   # layering preference: a's layer before b's
    label: str = ""
    card_a: str = ""       # text drawn beside the a end
    card_b: str = ""


@dataclass
class End:
    row: int
    col: int
    toward: str            # where a marker here points: "up", "down", "left", "right"


@dataclass
class Route:
    points: list[tuple[int, int]]   # (row, col) polyline from the a end to the b end
    a: End
    b: End
    label_at: tuple[int, int] | None = None
    card_a_at: tuple[int, int] | None = None
    card_b_at: tuple[int, int] | None = None


@dataclass
class Layout:
    positions: dict[str, tuple[int, int]]
    sizes: dict[str, tuple[int, int]]
    width: int
    height: int
    routes: list[Route | None] = field(default_factory=list)


# ── layering ──────────────────────────────────────────────────────

def _layering(names: list[str], links: list[Link]) -> tuple[dict[str, int], list[tuple[str, str, int]]]:
    """Return ({name: layer}, [(upper, lower, link_index)]) with every pair downwards.

    Cycles are broken by turning round the links a depth-first search meets
    going back up its own path; layers are the longest path from the
    sources, then a node with more links below it than above moves down
    next to its targets so its links stay short.
    """
    index = {n: i for i, n in enumerate(names)}
    wanted: list[tuple[str, str, int]] = []
    for i, link in enumerate(links):
        if link.a == link.b or link.a not in index or link.b not in index:
            continue
        u, v = (link.a, link.b) if link.a_above else (link.b, link.a)
        wanted.append((u, v, i))

    out: dict[str, list[tuple[str, int]]] = {n: [] for n in names}
    indeg = {n: 0 for n in names}
    for u, v, i in wanted:
        out[u].append((v, i))
        indeg[v] += 1

    state: dict[str, int] = {}
    back: set[int] = set()
    roots = [n for n in names if indeg[n] == 0] + [n for n in names if indeg[n]]
    for root in roots:
        if root in state:
            continue
        state[root] = 1
        stack = [(root, iter(out[root]))]
        while stack:
            node, it = stack[-1]
            for v, i in it:
                s = state.get(v)
                if s == 1:
                    back.add(i)
                elif s is None:
                    state[v] = 1
                    stack.append((v, iter(out[v])))
                    break
            else:
                state[node] = 2
                stack.pop()

    edges = [(v, u, i) if i in back else (u, v, i) for u, v, i in wanted]
    succ: dict[str, list[str]] = {n: [] for n in names}
    pred: dict[str, list[str]] = {n: [] for n in names}
    for u, v, _ in edges:
        succ[u].append(v)
        pred[v].append(u)

    remaining = {n: len(pred[n]) for n in names}
    ready = [n for n in names if remaining[n] == 0]
    topo: list[str] = []
    while ready:
        ready.sort(key=index.__getitem__)
        n = ready.pop(0)
        topo.append(n)
        for v in succ[n]:
            remaining[v] -= 1
            if remaining[v] == 0:
                ready.append(v)

    layer = {n: 0 for n in names}
    for n in topo:
        for v in succ[n]:
            layer[v] = max(layer[v], layer[n] + 1)
    for n in reversed(topo):
        if succ[n] and len(succ[n]) > len(pred[n]):
            layer[n] = max(layer[n], min(layer[v] for v in succ[n]) - 1)
    return layer, edges


# ── ordering ──────────────────────────────────────────────────────

def _crossings(segs: list[tuple[str, str, int]], pos: dict[str, int]) -> int:
    """Pairs of segments that cross: one starts left of the other and ends right of it.

    Counted as inversions with a Fenwick tree, in O(n log n).
    """
    pairs = sorted((pos[u], pos[l]) for u, l, _ in segs)
    size = max((l for _, l in pairs), default=0) + 1
    tree = [0] * (size + 1)
    count = 0
    for seen, (_, l) in enumerate(pairs):
        # Earlier segments start left of this one or level with it; those
        # level with it end left of it too, so every one ending right crosses.
        at, not_right = l + 1, 0
        while at > 0:
            not_right += tree[at]
            at -= at & -at
        count += seen - not_right
        at = l + 1
        while at <= size:
            tree[at] += 1
            at += at & -at
    return count


def _order(layers: list[list[str]], segs: list[list[tuple[str, str, int]]]) -> list[list[str]]:
    """Reorder each layer by the mean position of its neighbours to cut crossings.

    Keeps the best of a few up and down sweeps, the starting order on a tie.
    """
    def positions(ls: list[list[str]]) -> dict[str, int]:
        return {item: p for layer in ls for p, item in enumerate(layer)}

    def total(ls: list[list[str]]) -> int:
        pos = positions(ls)
        return sum(_crossings(s, pos) for s in segs)

    best, best_count = layers, total(layers)
    current = [list(layer) for layer in layers]
    for sweep in range(4):
        down = sweep % 2 == 0
        pos = positions(current)
        order = range(1, len(current)) if down else range(len(current) - 2, -1, -1)
        for k in order:
            near: dict[str, list[int]] = {}
            for u, l, _ in segs[k - 1] if down else segs[k]:
                mine, other = (l, u) if down else (u, l)
                near.setdefault(mine, []).append(pos[other])
            keyed = [(sum(near[it]) / len(near[it]) if it in near else pos[it], p, it)
                     for p, it in enumerate(current[k])]
            current[k] = [it for _, _, it in sorted(keyed)]
            pos.update({it: p for p, it in enumerate(current[k])})
        count = total(current)
        if count < best_count:
            best, best_count = [list(layer) for layer in current], count
        if best_count == 0:
            break
    return best


# ── shared building blocks ────────────────────────────────────────

@dataclass
class _Chain:
    link: int
    items: list[str]       # upper end, dummies, lower end
    upper_is_a: bool


def _build(names: list[str], links: list[Link]):
    layer, edges = _layering(names, links)
    depth = max(layer.values(), default=0) + 1
    layers: list[list[str]] = [[] for _ in range(depth)]

    # Start from breadth-first discovery order, which keeps a parent's
    # children together and in declaration order.
    succ: dict[str, list[str]] = {n: [] for n in names}
    has_pred = set()
    for u, v, _ in edges:
        succ[u].append(v)
        has_pred.add(v)
    seen: dict[str, int] = {}
    queue = [n for n in names if n not in has_pred]
    for n in queue:
        seen.setdefault(n, len(seen))
    head = 0
    while head < len(queue):
        n = queue[head]
        head += 1
        for v in succ[n]:
            if v not in seen:
                seen[v] = len(seen)
                queue.append(v)
    for n in names:
        seen.setdefault(n, len(seen))

    hint: dict[str, float] = dict(seen)
    chains: list[_Chain] = []
    for u, v, i in edges:
        items = [u]
        for k in range(layer[u] + 1, layer[v]):
            d = f"{_DUMMY}{i}:{k}"
            hint[d] = seen[u] + 0.5 + i / 1000
            layer[d] = k
            items.append(d)
        items.append(v)
        chains.append(_Chain(i, items, links[i].a == u))

    for item in sorted(layer, key=hint.__getitem__):
        layers[layer[item]].append(item)
    segs: list[list[tuple[str, str, int]]] = [[] for _ in range(max(depth - 1, 0))]
    for ch in chains:
        for j in range(len(ch.items) - 1):
            segs[layer[ch.items[j]]].append((ch.items[j], ch.items[j + 1], ch.link))
    layers = _order(layers, segs)
    return layers, segs, chains


def _ports(
    boxes: dict[str, tuple[int, int]],
    layers: list[list[str]],
    segs: list[list[tuple[str, str, int]]],
    links: list[Link],
    span_of: dict[str, int],
    min_spacing: int,
    card_room: bool,
    wide: dict[tuple[str, str], int] | None = None,
) -> dict[tuple[str, int, str], int]:
    """Offset from a box's centre for each link end on its two faces.

    Ends on one face are ordered by where the other end sits, so lines
    leaving one box do not cross, and spaced to leave room for a
    cardinality beside each line. Returns {(item, link, face): offset},
    face being "next" (towards the following layer) or "prev".
    """
    pos = {item: p for layer in layers for p, item in enumerate(layer)}
    faces: dict[tuple[str, str], list[tuple[int, int, int]]] = {}
    for k, boundary in enumerate(segs):
        for u, l, i in boundary:
            faces.setdefault((u, "next"), []).append((pos[l], i, k))
            faces.setdefault((l, "prev"), []).append((pos[u], i, k))
    offsets: dict[tuple[str, int, str], int] = {}
    for (item, face), ends in faces.items():
        ends.sort()
        n = len(ends)
        if item not in boxes or n == 1:
            for _, i, _ in ends:
                offsets[(item, i, face)] = 0
            continue
        cards = [0] * n
        if card_room:
            cards = [display_width(links[i].card_a if links[i].a == item else links[i].card_b)
                     for _, i, _ in ends]
        spacing = max(min_spacing, max(cards) + 2, (wide or {}).get((item, face), 0))
        # Ends spread evenly about the centre cell stay off both corners.
        centre = span_of[item] // 2
        room = 2 * min(centre - 1, span_of[item] - 2 - centre) + 1
        if (n - 1) * spacing > room:
            spacing = max(min(2, min_spacing), room // (n - 1))
        spread = [int((j - (n - 1) / 2) * spacing) for j in range(n)]
        # The last cardinality must still end inside the box.
        over = span_of[item] // 2 + spread[-1] + cards[-1] - (span_of[item] - 1)
        shift = -min(max(over, 0), span_of[item] // 2 + spread[0] - 1)
        for (_, i, _), off in zip(ends, spread):
            offsets[(item, i, face)] = off + shift
    return offsets


def _fit_ends(
    sizes: dict[str, tuple[int, int]],
    segs,
    links: list[Link],
    axis: int,
    spacing: dict[tuple[str, str], int] | None = None,
) -> dict[str, tuple[int, int]]:
    """Grow each box along ``axis`` (0 width, 1 height) so the ends on one
    face fit with a blank cell between them and the corners.

    Along a width the cardinality written beside each end must fit
    between it and the next end too, and ``spacing`` can ask for wider
    spacing on a face: {(item, face): cells from one end to the next}.
    """
    faces: dict[tuple[str, str], list[int]] = {}
    for boundary in segs:
        for u, l, i in boundary:
            faces.setdefault((u, "next"), []).append(i)
            faces.setdefault((l, "prev"), []).append(i)
    grown = dict(sizes)
    for (item, face), idxs in faces.items():
        if item not in grown:
            continue
        card = 0
        if axis == 0:
            card = max(display_width(links[i].card_a if links[i].a == item else links[i].card_b) for i in idxs)
        step = max(2, card + 1, (spacing or {}).get((item, face), 0))
        dims = list(grown[item])
        dims[axis] = max(dims[axis], (len(idxs) - 1) * step + 3)
        grown[item] = (dims[0], dims[1])
    return grown


def _assign_tracks(
    intervals: dict[int, tuple[int, int]],
    ends: dict[int, tuple[int, int]] | None = None,
) -> dict[int, int]:
    """Give each sideways run a track so overlapping runs never share one.

    ``intervals`` maps a key to the inclusive (low, high) span of a run;
    runs on one track are at least one blank cell apart so their corners do
    not touch. ``ends`` gives each run's (entry, exit) position across the
    gap: a run entering inside another must take an earlier track and one
    leaving inside it a later track, or it would cut through that run. A
    run entering where another leaves must take an earlier track too, or
    the two would share the row (column) between their tracks. Returns
    {key: track_index}.
    """
    keys = sorted(intervals, key=lambda k: intervals[k])
    after: dict[int, set[int]] = {k: set() for k in keys}
    if ends:
        by_entry = sorted((ends[j][0], j) for j in keys)
        by_leave = sorted((ends[j][1], j) for j in keys)
        entries = [e for e, _ in by_entry]
        leaves = [e for e, _ in by_leave]
        for i in keys:
            low, high = intervals[i]
            exit_i = ends[i][1]
            lo, hi = bisect_left(entries, exit_i), bisect_right(entries, exit_i)
            for _, j in by_entry[lo:hi]:
                if j != i:
                    after[i].add(j)
            for _, j in by_entry[bisect_right(entries, low):bisect_left(entries, high)]:
                if j != i and not low < ends[j][1] < high:
                    after[i].add(j)
            for _, j in by_leave[bisect_right(leaves, low):bisect_left(leaves, high)]:
                if j != i and not low < ends[j][0] < high and ends[j][0] != exit_i:
                    after[j].add(i)
    # Visit runs in an order that respects the constraints where it can.
    order: list[int] = []
    state: dict[int, int] = {}
    for root in keys:
        if root in state:
            continue
        stack = [(root, iter(sorted(after[root], key=lambda k: intervals[k])))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            for nxt in it:
                if nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter(sorted(after[nxt], key=lambda k: intervals[k]))))
                    break
            else:
                state[node] = 2
                order.append(node)
                stack.pop()
    tracks: list[list[tuple[int, int]]] = []
    result: dict[int, int] = {}
    for key in order:
        low, high = intervals[key]
        floor = max((result[j] + 1 for j in after[key] if j in result), default=0)
        t = floor
        while t < len(tracks) and any(not (h + 2 <= low or high + 2 <= l) for l, h in tracks[t]):
            t += 1
        if t == len(tracks):
            tracks.append([])
        tracks[t].append((low, high))
        result[key] = t
    return result


def _loop_room(link: Link) -> int:
    """Columns a self-loop's run needs between the box and its far side."""
    return display_width(link.card_a) + display_width(link.card_b) + 4


def _self_loops(names: set[str], links: list[Link]) -> dict[str, list[int]]:
    loops: dict[str, list[int]] = {}
    for i, link in enumerate(links):
        if link.a == link.b and link.a in names:
            loops.setdefault(link.a, []).append(i)
    return loops


# ── top to bottom ─────────────────────────────────────────────────

def _layout_tb(sizes: dict[str, tuple[int, int]], links: list[Link], gap: int) -> Layout:
    names = list(sizes)
    layers, segs, chains = _build(names, links)
    loops = _self_loops(set(names), links)
    sizes = dict(sizes)
    for node, idxs in loops.items():
        # Each loop leaves and comes back on rows of its own.
        w, h = sizes[node]
        sizes[node] = (w, max(h, 2 * len(idxs) + 1))
    asked = sizes
    wide: dict[tuple[str, str], int] = {}
    next_of = {layer[p]: layer[p + 1] for layer in layers for p in range(len(layer) - 1)}

    extra: dict[str, int] = {}
    for node, idxs in loops.items():
        # Loops sit to the right of their box, each label beyond its loop.
        far = max(_loop_room(links[i]) for i in idxs)
        extra[node] = far + max(display_width(links[i].label) + 3 for i in idxs) + 1

    def sep(left: str, right: str) -> int:
        base = gap if left in sizes and right in sizes else 2
        return max(base, extra.get(left, 0))

    for _attempt in range(3):
        sizes = _fit_ends(asked, segs, links, 0, wide)
        width_of = {item: (sizes[item][0] if item in sizes else 1) for layer in layers for item in layer}
        ports = _ports(sizes, layers, segs, links, width_of, 4, True, wide)
        x_of: dict[str, int] = {}
        widths = []
        for layer in layers:
            x = MARGIN
            for p, item in enumerate(layer):
                x_of[item] = x
                x += width_of[item]
                if p + 1 < len(layer):
                    x += sep(item, layer[p + 1])
                else:
                    x += extra.get(item, 0)
            widths.append(x - MARGIN)
        canvas_w = max(widths, default=0) + 2 * MARGIN
        for layer, w in zip(layers, widths):
            shift = (canvas_w - 2 * MARGIN - w) // 2
            for item in layer:
                x_of[item] += shift

        def col(item: str, link: int, face: str) -> int:
            if item not in sizes:
                return x_of[item]
            return x_of[item] + sizes[item][0] // 2 + ports.get((item, link, face), 0)

        geos: list[dict[int, tuple[int, int, str, str]]] = []
        tracks_of: list[dict[int, int]] = []
        for boundary in segs:
            geo = {i: (col(u, i, "next"), col(l, i, "prev"), u, l) for u, l, i in boundary}
            runs = {i: (min(g[0], g[1]), max(g[0], g[1])) for i, g in geo.items() if g[0] != g[1]}
            geos.append(geo)
            tracks_of.append(_assign_tracks(runs, {i: (g[0], g[1]) for i, g in geo.items()}))
        labels, upper_rows, lower_rows, need, wider = _place_labels(links, chains, geos, tracks_of, gap)
        wider = {face: sp for face, sp in wider.items() if sp > wide.get(face, 0)}
        if not need and not wider:
            break
        for item, more in need.items():
            extra[item] = sep(item, next_of[item]) + more
        wide.update(wider)

    # Rows: a gap holds the label rows beside lines leaving the box above,
    # the jog tracks, then the label rows beside lines entering the box below.
    layer_h = [max((sizes[it][1] for it in layer if it in sizes), default=1) for layer in layers]
    tops: list[int] = []
    first_track: list[int] = []
    first_lower: list[int] = []
    row = MARGIN
    for k in range(len(layers)):
        tops.append(row)
        row += layer_h[k]
        if k < len(segs):
            n_tracks = max(tracks_of[k].values(), default=-1) + 1
            first_track.append(row + 1 + upper_rows[k])
            first_lower.append(row + 1 + upper_rows[k] + n_tracks)
            row += max(gap, upper_rows[k] + n_tracks + lower_rows[k] + 2)
    canvas_h = tops[-1] + layer_h[-1] + MARGIN if layers else 1

    positions: dict[str, tuple[int, int]] = {}
    for k, layer in enumerate(layers):
        for item in layer:
            if item in sizes:
                positions[item] = (x_of[item], tops[k] + (layer_h[k] - sizes[item][1]) // 2)

    layer_index = {item: k for k, layer in enumerate(layers) for item in layer}
    routes: list[Route | None] = [None] * len(links)
    for ch in chains:
        upper, lower = ch.items[0], ch.items[-1]
        start_row = positions[upper][1] + sizes[upper][1]
        end_row = positions[lower][1] - 1
        first = layer_index[upper]
        x0 = geos[first][ch.link][0]
        pts = [(start_row, x0)]
        for j in range(len(ch.items) - 1):
            k = first + j
            xt, xb, _, _ = geos[k][ch.link]
            if ch.link in tracks_of[k]:
                r = first_track[k] + tracks_of[k][ch.link]
                pts += [(r, xt), (r, xb)]
        label_at = None
        if ch.link in labels:
            where, k, r, c = labels[ch.link]
            if where == "run":
                r += first_track[k]
            elif where == "lower":
                r += first_lower[k]
            elif where == "upper":
                r += tops[k] + layer_h[k] + 1
            elif where == "start":
                r = tops[k] + layer_h[k]
            else:
                r = tops[k + 1] - 1
            label_at = (r, c)
        xl = pts[-1][1]
        pts.append((end_row, xl))
        upper_end = End(start_row, x0, "up")
        lower_end = End(end_row, xl, "down")
        upper_card = (start_row, x0 + 1)
        lower_card = (end_row, xl + 1)
        if ch.upper_is_a:
            routes[ch.link] = Route(pts, upper_end, lower_end, label_at, upper_card, lower_card)
        else:
            routes[ch.link] = Route(pts[::-1], lower_end, upper_end, label_at, lower_card, upper_card)

    for node, idxs in loops.items():
        x, y = positions[node]
        w, h = sizes[node]
        far = max(_loop_room(links[i]) for i in idxs)
        for j, i in enumerate(idxs):
            routes[i] = _side_loop(links[i], x, y, w, far, j)
        canvas_w = max(canvas_w, x + w + extra[node] + MARGIN)

    for r in routes:
        if r is None:
            continue
        canvas_w = max(canvas_w, max(c for _, c in r.points) + 1 + MARGIN)
    return Layout(positions, sizes, canvas_w, canvas_h, routes)


def _place_labels(links, chains, geos, tracks_of, gap):
    """Decide where each label goes in a TB layout.

    In order of preference: on one of the link's own jogs where no line
    crosses it; in a label row beside the line where it enters its lower
    box; in a label row beside the line where it leaves its upper box.
    A label row holds only the vertical lines passing through it, so a
    label fits there if none of them lies under it. Label rows are only
    added while the gap stays as tall as ``gap`` asks; past that a label
    first tries the gap's first or last row, beside the cardinalities.
    When nothing fits, the label goes beside the entering line anyway,
    and the line in the way is asked to move: a neighbouring box moves
    over, or the line's own box spreads its ends apart. Returns ({link:
    (where, boundary, row, col)}, upper row counts, lower row counts,
    {item: extra columns needed to its right}, {(item, face): spacing}).
    """
    upper: list[list[list[tuple[int, int]]]] = [[] for _ in geos]
    lower: list[list[list[tuple[int, int]]]] = [[] for _ in geos]
    edge_rows: dict[tuple[str, int], list[tuple[int, int]]] = {}
    placed: dict[int, tuple[str, int, int, int]] = {}
    need: dict[str, int] = {}
    wider: dict[tuple[str, str], int] = {}
    chain_of = {ch.link: ch for ch in chains}

    def card(k: int, j: int, at: int) -> str:
        """Cardinality text beside link j's line at the top (0) or bottom (1) of gap k."""
        ch, link = chain_of[j], links[j]
        _, _, u, l = geos[k][j]
        if at == 0:
            return (link.card_a if ch.upper_is_a else link.card_b) if u == ch.items[0] else ""
        return (link.card_b if ch.upper_is_a else link.card_a) if l == ch.items[-1] else ""

    def in_row(i: int, where: str, k: int, w: int, grow: bool):
        at = 1 if where == "lower" else 0
        own = geos[k][i][at]
        cols = [g[at] for j, g in geos[k].items() if j != i]
        rows = lower[k] if where == "lower" else upper[k]
        n_tracks = max(tracks_of[k].values(), default=-1) + 1
        room = grow or len(upper[k]) + len(lower[k]) < gap - 2 - n_tracks
        for start in (own + 2, own - w - 1):
            if start >= 0 and not any(start - 1 <= c <= start + w for c in cols):
                r = _fit_row(rows, start, start + w - 1, room)
                if r is not None:
                    return (where, k, r, start)
        return None

    def in_edge_row(i: int, where: str, k: int, w: int):
        at = 1 if where == "end" else 0
        taken = edge_rows.setdefault((where, k), [])
        spans = [(g[at], g[at] + display_width(card(k, j, at))) for j, g in geos[k].items() if j != i]
        own = geos[k][i][at]
        own_end = own + display_width(card(k, i, at))
        for start in (own_end + 2, own - w - 1):
            if start >= 0 and all(start + w < s or start - 1 > e for s, e in spans + taken):
                taken.append((start, start + w - 1))
                return (where, k, 0, start)
        return None

    for ch in chains:
        label = links[ch.link].label
        if not label:
            continue
        w = display_width(label)
        i = ch.link
        first = next(k for k, geo in enumerate(geos) if i in geo and geo[i][2] == ch.items[0])
        last = first + len(ch.items) - 2
        spot = None
        for k in range(last, first - 1, -1):
            if i in tracks_of[k]:
                c = _free_span_on_run(i, tracks_of[k], geos[k], w)
                if c is not None:
                    spot = ("run", k, tracks_of[k][i], c)
                    break
        spot = (spot or in_row(i, "lower", last, w, False) or in_row(i, "upper", first, w, False)
                or in_edge_row(i, "start", first, w) or in_edge_row(i, "end", last, w)
                or in_row(i, "lower", last, w, True) or in_row(i, "upper", first, w, True))
        if spot is None:
            _, xb, top, owner = geos[last][i]
            blocking = [(g[1], g[3]) for j, g in geos[last].items() if j != i and xb < g[1] <= xb + w + 2]
            if blocking:
                c, o = min(blocking)
                if o != owner:
                    need[owner] = max(need.get(owner, 0), xb + w + 3 - c)
                else:
                    for face in ((owner, "prev"), (top, "next")):
                        wider[face] = max(wider.get(face, 0), w + 3)
            spot = ("lower", last, _fit_row(lower[last], xb + 2, xb + w + 1, True), xb + 2)
        placed[i] = spot
    return placed, [len(r) for r in upper], [len(r) for r in lower], need, wider


def _free_span_on_run(i, tracks, geo, w) -> int | None:
    """First column where a label of width w fits on run i between its
    corners without covering a line that crosses it, or None."""
    xt, xb, _, _ = geo[i]
    low, high = min(xt, xb), max(xt, xb)
    t = tracks[i]
    crossing = []
    for j, (xt_j, xb_j, _, _) in geo.items():
        if j == i:
            continue
        if j not in tracks or tracks[j] > t:
            crossing.append(xt_j)
        if j not in tracks or tracks[j] < t:
            crossing.append(xb_j)
    start = low + 2
    for c in sorted(crossing):
        if c < start - 1:
            continue
        if c <= start + w:
            start = c + 2
        else:
            break
    return start if start + w - 1 <= high - 2 else None


def _fit_row(rows: list[list[tuple[int, int]]], start: int, end: int, grow: bool) -> int | None:
    """Put a span in the first row it fits, adding a row only if ``grow``."""
    for r, spans in enumerate(rows):
        if all(end + 1 < s or start > e + 1 for s, e in spans):
            spans.append((start, end))
            return r
    if not grow:
        return None
    rows.append([(start, end)])
    return len(rows) - 1


def _side_loop(link: Link, x: int, y: int, w: int, reach: int, j: int) -> Route:
    """The j-th loop on a box's right side, out on row 2j and back on the
    row below; the first leaves from the top-right corner."""
    right = x + w - 1
    corner = right + reach
    out, back = y + 2 * j, y + 2 * j + 1
    pts = [(out, right if j == 0 else right + 1), (out, corner), (back, corner), (back, right + 1)]
    a = End(out, right + 1, "left")
    b = End(back, right + 1, "left")
    label_at = (back, corner + 2) if link.label else None
    return Route(pts, a, b, label_at, (out, right + 2), (back, right + 2))


def _under_spans(links: list[Link], idxs: list[int]) -> list[tuple[int, int]]:
    """(left, right) columns, from a box's left border, of each loop under
    it: side by side, each label after its loop and before the next."""
    spans = []
    left = 2
    for i in idxs:
        right = left + _loop_room(links[i])
        spans.append((left, right))
        left = right + 2 + (display_width(links[i].label) + 1 if links[i].label else 0)
    return spans


def _under_loop(link: Link, x: int, y: int, h: int, span: tuple[int, int]) -> Route:
    """A loop out of a box's bottom border and back into it."""
    bottom = y + h - 1
    left, right = x + span[0], x + span[1]
    low = bottom + 2
    pts = [(bottom + 1, left), (low, left), (low, right), (bottom + 1, right)]
    a = End(bottom + 1, left, "up")
    b = End(bottom + 1, right, "up")
    label_at = (low, right + 2) if link.label else None
    return Route(pts, a, b, label_at, (bottom + 1, left + 1),
                 (bottom + 1, right - display_width(link.card_b)))


# ── left to right ─────────────────────────────────────────────────

def _layout_lr(sizes: dict[str, tuple[int, int]], links: list[Link], gap: int) -> Layout:
    names = list(sizes)
    layers, segs, chains = _build(names, links)

    sizes = _fit_ends(sizes, segs, links, 1)
    loops = _self_loops(set(names), links)
    spans = {node: _under_spans(links, idxs) for node, idxs in loops.items()}
    for node, node_spans in spans.items():
        w, h = sizes[node]
        sizes[node] = (max(w, node_spans[-1][1] + 3), h)
    height_of = {item: (sizes[item][1] if item in sizes else 1) for layer in layers for item in layer}
    ports = _ports(sizes, layers, segs, links, height_of, 2, False)
    chain_of = {ch.link: ch for ch in chains}

    # Rows: boxes stacked in each column, columns centred vertically.
    y_of: dict[str, int] = {}
    heights = []
    for layer in layers:
        y = MARGIN
        for p, item in enumerate(layer):
            y_of[item] = y
            y += height_of[item]
            if item in loops:
                y += 2
            if p + 1 < len(layer):
                y += gap if item in sizes and layer[p + 1] in sizes else 1
        heights.append(y - MARGIN)
    canvas_h = max(heights, default=0) + 2 * MARGIN
    for layer, h in zip(layers, heights):
        shift = (canvas_h - 2 * MARGIN - h) // 2
        for item in layer:
            y_of[item] += shift

    def row(item: str, link: int, face: str) -> int:
        if item not in sizes:
            return y_of[item]
        return y_of[item] + sizes[item][1] // 2 + ports.get((item, link, face), 0)

    # Columns: each gap holds the cardinality beside the box it leaves, the
    # jog tracks, then the label and cardinality on the line into the box.
    plans = []
    for k, boundary in enumerate(segs):
        runs: dict[int, tuple[int, int]] = {}
        geo: dict[int, tuple[int, int]] = {}
        lead = 2
        tail = 3
        for u, l, i in boundary:
            link = links[i]
            yl, yr = row(u, i, "next"), row(l, i, "prev")
            geo[i] = (yl, yr)
            if yl != yr:
                runs[i] = (min(yl, yr), max(yl, yr))
            near_u = link.card_a if chain_of[i].upper_is_a else link.card_b
            near_l = link.card_b if chain_of[i].upper_is_a else link.card_a
            if u in sizes:
                lead = max(lead, display_width(near_u) + 2)
            if l in sizes:
                body = display_width(link.label) + 2 if link.label and chain_of[i].items[-1] == l else 0
                tail = max(tail, body + display_width(near_l) + 3)
        tracks = _assign_tracks(runs, geo)
        n_tracks = max(tracks.values(), default=-1) + 1
        plans.append((geo, tracks, lead, n_tracks, tail))

    layer_w = [max((sizes[it][0] for it in layer if it in sizes), default=1) for layer in layers]
    # A loop label can run past its column; the gap's jogs start beyond it.
    for k, plan in enumerate(plans):
        over = 0
        for item in layers[k]:
            for i, (_, right) in zip(loops.get(item, ()), spans.get(item, ())):
                if links[i].label:
                    end = (layer_w[k] - sizes[item][0]) // 2 + right + 1 + display_width(links[i].label)
                    over = max(over, end - (layer_w[k] - 1))
        if over:
            geo, tracks, lead, n_tracks, tail = plan
            plans[k] = (geo, tracks, max(lead, over + 1), n_tracks, tail)
    lefts: list[int] = []
    x = MARGIN
    for k in range(len(layers)):
        lefts.append(x)
        if k < len(plans):
            _, _, lead, n_tracks, tail = plans[k]
            x += layer_w[k] + max(gap, lead + n_tracks + tail)
        else:
            x += layer_w[k]
    canvas_w = x + MARGIN

    positions: dict[str, tuple[int, int]] = {}
    for k, layer in enumerate(layers):
        for item in layer:
            if item in sizes:
                positions[item] = (lefts[k] + (layer_w[k] - sizes[item][0]) // 2, y_of[item])

    layer_index = {item: k for k, layer in enumerate(layers) for item in layer}
    routes: list[Route | None] = [None] * len(links)
    for ch in chains:
        upper, lower = ch.items[0], ch.items[-1]
        first = layer_index[upper]
        start_col = positions[upper][0] + sizes[upper][0]
        end_col = positions[lower][0] - 1
        y0 = plans[first][0][ch.link][0]
        pts = [(y0, start_col)]
        for j in range(len(ch.items) - 1):
            k = first + j
            geo, tracks, lead, _, _ = plans[k]
            yl, yr = geo[ch.link]
            if ch.link in tracks:
                c = lefts[k] + layer_w[k] + lead + tracks[ch.link]
                pts += [(yl, c), (yr, c)]
        yl_last = pts[-1][0]
        pts.append((yl_last, end_col))
        link = links[ch.link]
        label_at = None
        near_l = link.card_b if ch.upper_is_a else link.card_a
        if link.label:
            w = display_width(link.label)
            seg_start = pts[-2][1] if len(pts) > 2 else start_col
            room_end = end_col - display_width(near_l) - 1
            label_at = (yl_last, max(seg_start + 2, room_end - w - 1))
        upper_end = End(y0, start_col, "left")
        lower_end = End(yl_last, end_col, "right")
        upper_card = _beside(upper_end, link.card_a if ch.upper_is_a else link.card_b)
        lower_card = _beside(lower_end, near_l)
        if ch.upper_is_a:
            routes[ch.link] = Route(pts, upper_end, lower_end, label_at, upper_card, lower_card)
        else:
            routes[ch.link] = Route(pts[::-1], lower_end, upper_end, label_at, lower_card, upper_card)

    for node, idxs in loops.items():
        x, y = positions[node]
        w, h = sizes[node]
        for i, span in zip(idxs, spans[node]):
            routes[i] = _under_loop(links[i], x, y, h, span)
            if links[i].label:
                canvas_w = max(canvas_w, routes[i].label_at[1] + display_width(links[i].label) + MARGIN)
        canvas_h = max(canvas_h, y + h + 2 + MARGIN)
    return Layout(positions, sizes, canvas_w, canvas_h, routes)


# ── entry point and drawing ───────────────────────────────────────

def layout(sizes: dict[str, tuple[int, int]], links: list[Link], gap: int, direction: str = "TB") -> Layout:
    """Place boxes of the given sizes and route the links between them.

    ``direction`` is TB, BT, LR or RL; BT and RL are TB and LR mirrored.
    Boxes can come back wider (TB) or taller (LR) than asked, to fit the
    lines on their faces; draw them at ``Layout.sizes``.
    """
    if not sizes:
        return Layout({}, {}, 1, 1, [None] * len(links))
    horizontal = direction in ("LR", "RL")
    result = (_layout_lr if horizontal else _layout_tb)(sizes, links, gap)
    if direction == "BT":
        _mirror(result, rows=True, links=links)
    elif direction == "RL":
        _mirror(result, rows=False, links=links)
    return result


_FLIP = {"up": "down", "down": "up", "left": "right", "right": "left"}


def _mirror(lay: Layout, rows: bool, links: list[Link]) -> None:
    span = lay.height if rows else lay.width

    def m(r: int, c: int) -> tuple[int, int]:
        return (span - 1 - r, c) if rows else (r, span - 1 - c)

    for name, (x, y) in lay.positions.items():
        w, h = lay.sizes[name]
        lay.positions[name] = (x, span - y - h) if rows else (span - x - w, y)
    for link, r in zip(links, lay.routes):
        if r is None:
            continue
        r.points = [m(*p) for p in r.points]
        for end in (r.a, r.b):
            end.row, end.col = m(end.row, end.col)
            if (rows and end.toward in ("up", "down")) or (not rows and end.toward in ("left", "right")):
                end.toward = _FLIP[end.toward]

        def text(at, s):
            if at is None:
                return None
            if rows:
                return (span - 1 - at[0], at[1])
            return (at[0], span - at[1] - display_width(s))

        r.label_at = text(r.label_at, link.label)
        if rows:
            r.card_a_at, r.card_b_at = text(r.card_a_at, link.card_a), text(r.card_b_at, link.card_b)
        else:
            # A cardinality on a horizontal line sits just inside its end;
            # mirrored it must still start next to that end.
            r.card_a_at = _beside(r.a, link.card_a) if r.a.toward in ("left", "right") else text(r.card_a_at, link.card_a)
            r.card_b_at = _beside(r.b, link.card_b) if r.b.toward in ("left", "right") else text(r.card_b_at, link.card_b)


def _beside(end: End, text: str) -> tuple[int, int]:
    if end.toward == "left":       # the box is to the left: text starts right of the end
        return (end.row, end.col + 1)
    return (end.row, end.col - display_width(text))


def put_label(canvas, at: tuple[int, int], text: str) -> None:
    """Write a label or cardinality; its spaces clear any line under them,
    so a label on a line reads ``─tracks loans─``."""
    row, col = at
    offset = 0
    for ch in text:
        if ch == " ":
            canvas.blank(row, col + offset)
        offset += display_width(ch)
    canvas.put_text(row, col, text, style="edge_label", grow=True)


def attach_end(canvas, route: Route, end: End, cs) -> None:
    """Join a line that stops beside a box to the box's border with a tee.

    Only a self-loop needs this: its ends stop next to the border, which
    is drawn later and would otherwise just touch the line.
    """
    first, last = route.points[0], route.points[-1]
    if (end.row, end.col) not in (first, last):
        return
    row, col, tee = {
        "left": (end.row, end.col - 1, cs.tee_right),
        "right": (end.row, end.col + 1, cs.tee_left),
        "up": (end.row - 1, end.col, cs.tee_down),
        "down": (end.row + 1, end.col, cs.tee_up),
    }[end.toward]
    canvas.put(row, col, tee)


_DIRS = {(-1, 0): 1, (1, 0): 2, (0, -1): 4, (0, 1): 8}  # up, down, left, right
_CORNER = {2 | 8: "┌", 2 | 4: "┐", 1 | 8: "└", 1 | 4: "┘"}


def draw_route(canvas, route: Route, h_char: str, v_char: str, corner_char: str | None, style: str = "edge") -> None:
    """Draw a route's polyline. ``corner_char`` replaces every bend (ASCII);
    None draws box-drawing corners that merge with lines they meet."""
    pts = route.points
    max_c = max(c for _, c in pts)
    max_r = max(r for r, _ in pts)
    if max_c >= canvas.width or max_r >= canvas.height:
        canvas.resize(max(canvas.width, max_c + 1), max(canvas.height, max_r + 1))
    bends = set()
    for j in range(1, len(pts) - 1):
        (r0, c0), (r1, c1), (r2, c2) = pts[j - 1], pts[j], pts[j + 1]
        if (r0 == r1 == r2) or (c0 == c1 == c2):
            continue
        bends.add(j)
    put = canvas.put
    for j in range(len(pts) - 1):
        (r1, c1), (r2, c2) = pts[j], pts[j + 1]
        if (r1, c1) == (r2, c2):
            continue
        # Bends are drawn last, as corners.
        vertical = c1 == c2
        start, stop = (r1, r2) if vertical else (c1, c2)
        step = 1 if stop > start else -1
        if j in bends:
            start += step
        if j + 1 not in bends:
            stop += step
        if vertical:
            for r in range(start, stop, step):
                put(r, c1, v_char, style=style)
        else:
            for c in range(start, stop, step):
                put(r1, c, h_char, style=style)
    for j in bends:
        (r0, c0), (r1, c1), (r2, c2) = pts[j - 1], pts[j], pts[j + 1]
        d = 0
        for (ra, ca) in ((r0, c0), (r2, c2)):
            dr = (ra > r1) - (ra < r1)
            dc = (ca > c1) - (ca < c1)
            d |= _DIRS[(dr, dc)]
        if corner_char is not None:
            canvas.put(r1, c1, corner_char, merge=False, style=style)
        else:
            canvas.put(r1, c1, _CORNER[d], style=style)
