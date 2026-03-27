"""Renderer for treemap diagrams.

Renders a Treemap as nested rectangles on a Canvas using a
squarified layout algorithm for readable proportions.
Section nodes use dashed borders; leaf nodes use solid borders.
"""
from __future__ import annotations

from ..model.treemap import Treemap, TreemapNode
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from ..utils import display_width

_MIN_BOX_W = 4
_MIN_BOX_H = 3
_GAP = 1  # gap between sibling boxes
_LABEL_PAD = 0  # minimum padding around label text inside a box


def render_treemap(
    diagram: Treemap,
    *,
    use_ascii: bool = False,
) -> Canvas:
    """Render a Treemap model to a Canvas."""
    cs = ASCII if use_ascii else UNICODE

    if not diagram.roots:
        return Canvas(1, 1)

    total = diagram.total_value
    if total <= 0:
        return Canvas(1, 1)

    canvas_h = _compute_height(diagram.roots)
    min_w = _compute_min_width(diagram.roots)

    # Scale width: proportional for small diagrams, tight for large ones
    # Cap at 120 unless the minimum requires more
    canvas_w = max(min_w, min(120, max(60, int(min_w * 1.6))))

    canvas = Canvas(canvas_w, canvas_h)
    _layout_nodes(canvas, cs, diagram.roots, 0, 0, canvas_w, canvas_h, depth=0)

    return canvas


def _compute_height(nodes: list[TreemapNode]) -> int:
    """Compute the minimum height needed to render a list of nodes."""
    max_h = 0
    for node in nodes:
        if node.children:
            child_h = _compute_height(node.children)
            h = child_h + 4  # top border + label + child area + bottom border
        else:
            h = 4  # top border + label + value + bottom border
        max_h = max(max_h, h)
    return max_h


def _compute_min_width(nodes: list[TreemapNode]) -> int:
    """Compute the minimum width needed to render sibling nodes side by side."""
    total = 0
    for node in nodes:
        if node.children:
            child_w = _compute_min_width(node.children)
            # borders (2) + child content
            node_w = child_w + 2
        else:
            # borders (2) + label padding
            label_w = display_width(node.label) + _LABEL_PAD
            node_w = max(_MIN_BOX_W, label_w + 2)
        total += node_w

    # Add gaps between siblings
    total += _GAP * max(0, len(nodes) - 1)
    return total


def _layout_nodes(
    canvas: Canvas,
    cs: CharSet,
    nodes: list[TreemapNode],
    x: int, y: int, w: int, h: int,
    depth: int,
) -> None:
    """Recursively lay out nodes into the given rectangle."""
    if not nodes or w < _MIN_BOX_W or h < _MIN_BOX_H:
        return

    total = sum(n.total_value for n in nodes)
    if total <= 0:
        return

    # Sort by value descending for better layout
    sorted_nodes = sorted(nodes, key=lambda n: n.total_value, reverse=True)

    _slice_layout(canvas, cs, sorted_nodes, x, y, w, h, total, depth)


def _slice_layout(
    canvas: Canvas,
    cs: CharSet,
    nodes: list[TreemapNode],
    x: int, y: int, w: int, h: int,
    total: float,
    depth: int,
) -> None:
    """Lay out nodes side by side horizontally with gaps."""
    n_gaps = len(nodes) - 1
    total_gap_w = _GAP * n_gaps
    usable_w = w - total_gap_w

    if usable_w < _MIN_BOX_W * len(nodes):
        # Not enough space for gaps, drop them
        total_gap_w = 0
        usable_w = w
        n_gaps = 0

    # Compute minimum widths for each node
    min_widths = []
    for node in nodes:
        if node.children:
            mw = _compute_min_width(node.children) + 2
        else:
            mw = _MIN_BOX_W
        min_widths.append(mw)

    # Distribute width proportionally, respecting minimums
    raw_sizes = []
    for node in nodes:
        raw_sizes.append(node.total_value / total * usable_w)

    # Adjust: ensure minimums are met, redistribute excess
    sizes = list(raw_sizes)
    for _ in range(3):  # iterate to stabilize
        deficit = 0
        surplus_total = 0
        for i in range(len(sizes)):
            if sizes[i] < min_widths[i]:
                deficit += min_widths[i] - sizes[i]
                sizes[i] = min_widths[i]
            else:
                surplus_total += sizes[i] - min_widths[i]
        if deficit > 0 and surplus_total > 0:
            scale = max(0, 1 - deficit / surplus_total)
            for i in range(len(sizes)):
                if sizes[i] > min_widths[i]:
                    excess = sizes[i] - min_widths[i]
                    sizes[i] = min_widths[i] + excess * scale

    # Round to integers
    int_sizes = [max(min_widths[i], round(sizes[i])) for i in range(len(sizes))]

    # Fix total to match usable_w
    current_total = sum(int_sizes)
    if current_total != usable_w:
        diff = usable_w - current_total
        # Adjust the largest node
        largest_idx = max(range(len(int_sizes)), key=lambda i: int_sizes[i])
        int_sizes[largest_idx] = max(min_widths[largest_idx], int_sizes[largest_idx] + diff)

    # Draw each node
    pos_x = x
    for i, node in enumerate(nodes):
        bw = int_sizes[i]
        # Clamp to available space
        bw = min(bw, x + w - pos_x)
        if bw < _MIN_BOX_W:
            break

        _draw_node(canvas, cs, node, pos_x, y, bw, h, depth)
        pos_x += bw + (_GAP if i < n_gaps else 0)


def _draw_node(
    canvas: Canvas,
    cs: CharSet,
    node: TreemapNode,
    x: int, y: int, w: int, h: int,
    depth: int,
) -> None:
    """Draw a single node box and recurse into children."""
    if w < _MIN_BOX_W or h < _MIN_BOX_H:
        return

    is_section = bool(node.children)

    # Section nodes (with children) get dashed borders
    if is_section:
        hz = cs.line_dotted_h
        vt = cs.line_dotted_v
    else:
        hz = cs.horizontal
        vt = cs.vertical

    tl = cs.top_left
    tr = cs.top_right
    bl = cs.bottom_left
    br = cs.bottom_right

    style = "subgraph" if is_section else "node"

    # Top border
    canvas.put(y, x, tl, merge=False, style=style)
    for c in range(x + 1, x + w - 1):
        canvas.put(y, c, hz, merge=False, style=style)
    canvas.put(y, x + w - 1, tr, merge=False, style=style)

    # Bottom border
    canvas.put(y + h - 1, x, bl, merge=False, style=style)
    for c in range(x + 1, x + w - 1):
        canvas.put(y + h - 1, c, hz, merge=False, style=style)
    canvas.put(y + h - 1, x + w - 1, br, merge=False, style=style)

    # Side borders
    for r in range(y + 1, y + h - 1):
        canvas.put(r, x, vt, merge=False, style=style)
        canvas.put(r, x + w - 1, vt, merge=False, style=style)

    # Label — centered on the first inner row
    label = node.label
    inner_w = w - 2
    if display_width(label) > inner_w:
        label = label[:inner_w - 1] + "…" if inner_w > 1 else label[:inner_w]
    label_col = x + 1 + max(0, (inner_w - display_width(label)) // 2)
    canvas.put_text(y + 1, label_col, label, style="label")

    # Value (for leaves only)
    if not node.children and node.value > 0 and h >= 4:
        val_str = f"{node.value:g}"
        if len(val_str) > inner_w:
            val_str = val_str[:inner_w]
        val_col = x + 1 + max(0, (inner_w - len(val_str)) // 2)
        canvas.put_text(y + 2, val_col, val_str, style="edge_label")

    # Recurse into children
    if node.children:
        inner_x = x + 1
        inner_y = y + 2  # skip border + label
        inner_w_val = w - 2
        inner_h = h - 3  # top border + label + bottom border

        if inner_w_val >= _MIN_BOX_W and inner_h >= _MIN_BOX_H:
            _layout_nodes(canvas, cs, node.children, inner_x, inner_y, inner_w_val, inner_h, depth + 1)
