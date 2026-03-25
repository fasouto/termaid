"""Renderer for mindmap diagrams.

Renders a tree radiating from a central root node. Children branch to
the right by default. When the root has many children (> threshold),
the first few overflow to the left so the diagram stays balanced.

Each subtree is rendered recursively as a block of text lines with a
designated connection row where the parent attaches.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model.mindmap import Mindmap, MindmapNode
from .canvas import Canvas

# When root has more children than this, spill some to the left
_OVERFLOW_THRESHOLD = 6


@dataclass(frozen=True)
class _Chars:
    """Branch drawing characters, varying by ascii/rounded mode."""
    h: str    # horizontal line
    v: str    # vertical continuation
    tl: str   # top-left corner (first child)
    bl: str   # bottom-left corner (last child)
    tee: str  # tee junction (middle child)
    tj: str   # junction when connect row falls between children
    # mirrored (for left-branching)
    tr: str   # top-right
    br: str   # bottom-right
    tee_l: str  # left-facing tee
    tj_l: str   # left-facing junction


def _make_chars(use_ascii: bool, rounded: bool) -> _Chars:
    if use_ascii:
        return _Chars(
            h="-", v="|", tl="+", bl="+", tee="+", tj="+",
            tr="+", br="+", tee_l="+", tj_l="+",
        )
    if rounded:
        return _Chars(
            h="─", v="│", tl="╭", bl="╰", tee="├", tj="┤",
            tr="╮", br="╯", tee_l="┤", tj_l="├",
        )
    return _Chars(
        h="─", v="│", tl="┌", bl="└", tee="├", tj="┤",
        tr="┐", br="┘", tee_l="┤", tj_l="├",
    )


def render_mindmap(
    diagram: Mindmap,
    *,
    use_ascii: bool = False,
    rounded: bool = True,
) -> Canvas:
    """Render a Mindmap model to a Canvas."""
    if diagram.root is None:
        return Canvas(1, 1)

    ch = _make_chars(use_ascii, rounded)
    root = diagram.root

    if not root.children:
        lines = [root.label]
    else:
        left_children, right_children = _split_children(root.children)
        if not left_children:
            right_block, _ = _render_subtree_right(
                MindmapNode(label=root.label, children=right_children), ch)
            lines = right_block
        else:
            lines = _render_both_sides(root.label, left_children, right_children, ch)

    width = max((len(line) for line in lines), default=1)
    height = len(lines)
    canvas = Canvas(width + 1, height)
    for r, line in enumerate(lines):
        canvas.put_text(r, 0, line, style="node")
    return canvas


def _split_children(
    children: list[MindmapNode],
) -> tuple[list[MindmapNode], list[MindmapNode]]:
    """Split children into left-overflow and right groups."""
    if len(children) <= _OVERFLOW_THRESHOLD:
        return [], children
    n_left = len(children) // 3
    n_left = max(1, min(n_left, len(children) - 1))
    return children[:n_left], children[n_left:]


# ---------------------------------------------------------------------------
# Right-branching subtree
# ---------------------------------------------------------------------------

def _render_subtree_right(node: MindmapNode, ch: _Chars) -> tuple[list[str], int]:
    """Render a node with children branching to the right.

    Returns (lines, connect_row).
    """
    if not node.children:
        return [node.label], 0

    child_block, child_conn = _stack_right(node.children, ch)

    connector = node.label + " " + ch.h + ch.h
    pad = " " * len(connector)
    result: list[str] = []
    for i, line in enumerate(child_block):
        if i == child_conn:
            result.append(connector + line)
        else:
            result.append(pad + line)
    return result, child_conn


def _stack_right(children: list[MindmapNode], ch: _Chars) -> tuple[list[str], int]:
    """Stack child subtrees vertically with branch chars on the left."""
    if len(children) == 1:
        sub, sc = _render_subtree_right(children[0], ch)
        result = []
        for i, line in enumerate(sub):
            if i == sc:
                result.append(ch.h + ch.h + " " + line)
            else:
                result.append("   " + line)
        return result, sc

    blocks: list[tuple[list[str], int]] = []
    for child in children:
        blocks.append(_render_subtree_right(child, ch))

    result: list[str] = []
    conn_rows: list[int] = []

    for idx, (block, bc) in enumerate(blocks):
        is_first = idx == 0
        is_last = idx == len(blocks) - 1
        base = len(result)

        for li, line in enumerate(block):
            if li == bc:
                conn_rows.append(base + li)
                if is_first:
                    result.append(ch.tl + ch.h + " " + line)
                elif is_last:
                    result.append(ch.bl + ch.h + " " + line)
                else:
                    result.append(ch.tee + ch.h + " " + line)
            else:
                result.append(ch.v + "  " + line)

    # Replace │ with space for rows outside the connection range
    first_conn = conn_rows[0]
    last_conn = conn_rows[-1]
    for i in range(0, first_conn):
        if result[i][0] == ch.v:
            result[i] = " " + result[i][1:]
    for i in range(last_conn + 1, len(result)):
        if result[i][0] == ch.v:
            result[i] = " " + result[i][1:]

    mid = (conn_rows[0] + conn_rows[-1]) // 2
    if mid not in conn_rows:
        if result[mid][0] == ch.v:
            result[mid] = ch.tj + result[mid][1:]

    return result, mid


# ---------------------------------------------------------------------------
# Left-branching subtree (mirrored)
# ---------------------------------------------------------------------------

def _render_subtree_left(node: MindmapNode, ch: _Chars) -> tuple[list[str], int]:
    """Render a node with children branching to the left (mirrored)."""
    if not node.children:
        return [node.label], 0

    child_block, child_conn = _stack_left(node.children, ch)
    child_width = max(len(line) for line in child_block)
    child_block = [line.rjust(child_width) for line in child_block]

    connector = ch.h + ch.h + " " + node.label
    pad = " " * len(connector)
    result: list[str] = []
    for i, line in enumerate(child_block):
        if i == child_conn:
            result.append(line + connector)
        else:
            result.append(line + pad)
    return result, child_conn


def _stack_left(children: list[MindmapNode], ch: _Chars) -> tuple[list[str], int]:
    """Stack child subtrees with branch chars on the right (mirrored)."""
    if len(children) == 1:
        sub, sc = _render_subtree_left(children[0], ch)
        w = max(len(line) for line in sub)
        result = []
        for i, line in enumerate(sub):
            if i == sc:
                result.append(line.rjust(w) + " " + ch.h + ch.h)
            else:
                result.append(line.rjust(w) + "   ")
        return result, sc

    blocks: list[tuple[list[str], int]] = []
    for child in children:
        blocks.append(_render_subtree_left(child, ch))

    max_w = max(max(len(line) for line in block) for block, _ in blocks)
    result: list[str] = []
    conn_rows: list[int] = []

    for idx, (block, bc) in enumerate(blocks):
        is_first = idx == 0
        is_last = idx == len(blocks) - 1
        base = len(result)

        for li, line in enumerate(block):
            padded = line.rjust(max_w)
            if li == bc:
                conn_rows.append(base + li)
                if is_first:
                    result.append(padded + " " + ch.h + ch.tr)
                elif is_last:
                    result.append(padded + " " + ch.h + ch.br)
                else:
                    result.append(padded + " " + ch.h + ch.tee_l)
            else:
                if is_last:
                    result.append(padded + "   ")
                else:
                    result.append(padded + "  " + ch.v)

    first_conn = conn_rows[0]
    last_conn = conn_rows[-1]
    for i in range(0, first_conn):
        if result[i].endswith(ch.v):
            result[i] = result[i][:-1] + " "
    for i in range(last_conn + 1, len(result)):
        if result[i].endswith(ch.v):
            result[i] = result[i][:-1] + " "

    mid = (conn_rows[0] + conn_rows[-1]) // 2
    if mid not in conn_rows:
        if result[mid].endswith(ch.v):
            result[mid] = result[mid][:-1] + ch.tj_l

    return result, mid


# ---------------------------------------------------------------------------
# Root with both sides
# ---------------------------------------------------------------------------

def _render_both_sides(
    root_label: str,
    left_children: list[MindmapNode],
    right_children: list[MindmapNode],
    ch: _Chars,
) -> list[str]:
    """Render root in the center with left and right subtrees."""
    right_block, _ = _stack_right(right_children, ch)
    left_block, _ = _stack_left(left_children, ch)

    left_width = max((len(line) for line in left_block), default=0)
    rh = len(right_block)
    lh = len(left_block)
    total = max(rh, lh)

    r_off = (total - rh) // 2
    l_off = (total - lh) // 2
    root_row = total // 2

    root_part = ch.h + ch.h + " " + root_label + " " + ch.h + ch.h
    pad = " " * len(root_part)

    result: list[str] = []
    for row in range(total):
        li = row - l_off
        left = left_block[li].ljust(left_width) if 0 <= li < lh else " " * left_width
        ri = row - r_off
        right = right_block[ri] if 0 <= ri < rh else ""
        center = root_part if row == root_row else pad
        result.append(left + center + right)

    return result
