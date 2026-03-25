"""Draw orchestrator: combines layout, routing, and rendering into final output.

Drawing order (back to front):
1. Subgraphs (background)
2. Nodes (boxes)
3. Edge lines
4. Edge corners
5. Arrow heads
6. T-junctions (where edges leave nodes)
7. Edge labels
8. Subgraph labels
"""
from __future__ import annotations

from ..graph.model import ArrowType, Direction, EdgeStyle, Graph, GraphNote
from ..graph.shapes import NodeShape
from ..layout.grid import GridLayout, NodePlacement, compute_layout
from ..routing.router import AttachDir, RoutedEdge, route_edges
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from .shapes import SHAPE_RENDERERS, draw_rectangle


def render_graph(
    graph: Graph,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    gap: int = 4,
) -> str:
    """Render a graph to a string.

    Args:
        graph: The parsed graph model
        use_ascii: Use ASCII characters instead of Unicode
        padding_x: Horizontal padding inside node boxes
        padding_y: Vertical padding inside node boxes
        rounded_edges: Use rounded corners on edge turns (╭╮╰╯ vs ┌┐└┘)
        gap: Space between nodes (default: 4)

    Returns:
        The rendered diagram as a string
    """
    canvas = render_graph_canvas(
        graph, use_ascii=use_ascii, padding_x=padding_x, padding_y=padding_y,
        rounded_edges=rounded_edges, gap=gap,
    )
    if canvas is None:
        return ""
    return canvas.to_string()


def render_graph_canvas(
    graph: Graph,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    gap: int = 4,
) -> Canvas | None:
    """Render a graph and return the Canvas (with style info).

    Returns None for empty graphs.
    """
    if not graph.node_order:
        return None

    cs = ASCII if use_ascii else UNICODE

    # Need to handle BT/RL by rendering as TB/LR then flipping
    direction = graph.direction
    needs_v_flip = direction == Direction.BT
    needs_h_flip = direction == Direction.RL

    # Normalize direction for layout
    if needs_v_flip:
        graph.direction = Direction.TB
    elif needs_h_flip:
        graph.direction = Direction.LR

    # Layout
    layout = compute_layout(graph, padding_x, padding_y, gap)

    # Route edges
    routed = route_edges(graph, layout)

    # Create canvas (add some margin)
    # Account for edge paths that may extend beyond node boundaries
    # (e.g. back edges routed to the right/below of all nodes)
    width = layout.canvas_width + 4
    height = layout.canvas_height + 4
    for re in routed:
        for x, y in re.draw_path:
            width = max(width, x + 2)
            height = max(height, y + 2)
    canvas = Canvas(width, height)

    # 1. Draw subgraph borders (background layer)
    _draw_subgraph_borders(canvas, layout, cs)

    # 2. Draw nodes
    _draw_nodes(canvas, graph, layout, cs)

    # 3. Draw edges
    _draw_edges(canvas, graph, layout, routed, cs, rounded_edges=rounded_edges)

    # 4. Draw subgraph labels (on top of everything else)
    _draw_subgraph_labels(canvas, layout, cs)

    # 5. Draw notes (on top of everything else)
    _draw_notes(canvas, graph, layout, cs)

    # Flip if needed
    if needs_v_flip:
        canvas.flip_vertical()
        graph.direction = Direction.BT
    elif needs_h_flip:
        canvas.flip_horizontal()
        graph.direction = Direction.RL

    return canvas


def _draw_subgraph_borders(canvas: Canvas, layout: GridLayout, cs: CharSet) -> None:
    """Draw subgraph border boxes (background layer)."""
    for sb in layout.subgraph_bounds:
        x, y = sb.x, sb.y
        w, h = sb.width, sb.height

        if w <= 0 or h <= 0:
            continue

        # Ensure bounds are valid
        x = max(0, x)
        y = max(0, y)

        # Top border
        canvas.put(y, x, cs.sg_top_left, style="subgraph")
        for c in range(x + 1, x + w - 1):
            canvas.put(y, c, cs.sg_horizontal, style="subgraph")
        canvas.put(y, x + w - 1, cs.sg_top_right, style="subgraph")

        # Bottom border
        canvas.put(y + h - 1, x, cs.sg_bottom_left, style="subgraph")
        for c in range(x + 1, x + w - 1):
            canvas.put(y + h - 1, c, cs.sg_horizontal, style="subgraph")
        canvas.put(y + h - 1, x + w - 1, cs.sg_bottom_right, style="subgraph")

        # Side borders
        for r in range(y + 1, y + h - 1):
            canvas.put(r, x, cs.sg_vertical, style="subgraph")
            canvas.put(r, x + w - 1, cs.sg_vertical, style="subgraph")


def _draw_subgraph_labels(canvas: Canvas, layout: GridLayout, cs: CharSet) -> None:
    """Draw subgraph labels (on top of everything else)."""
    for sb in layout.subgraph_bounds:
        x, y = sb.x, sb.y
        w, h = sb.width, sb.height

        if w <= 0 or h <= 0:
            continue

        x = max(0, x)
        y = max(0, y)

        label = sb.subgraph.label
        if label:
            canvas.put_text(y + 1, x + 2, label, style="subgraph_label")


def _draw_nodes(canvas: Canvas, graph: Graph, layout: GridLayout, cs: CharSet) -> None:
    """Draw all node boxes."""
    for nid in graph.node_order:
        if nid not in layout.placements:
            continue
        node = graph.nodes[nid]
        p = layout.placements[nid]

        # Resolve style key: inline style > :::className > classDef default > "node"
        if nid in graph.node_styles:
            style = f"nodestyle:{nid}"
        elif node.style_class and node.style_class in graph.class_defs:
            style = f"class:{node.style_class}"
        elif "default" in graph.class_defs:
            style = "class:default"
        else:
            style = "node"

        renderer = SHAPE_RENDERERS.get(node.shape, SHAPE_RENDERERS[NodeShape.RECTANGLE])
        renderer(canvas, p.draw_x, p.draw_y, p.draw_width, p.draw_height, node.label, cs, style=style)

        # Overwrite label with styled text if markdown segments exist
        if node.label_segments:
            label_row = p.draw_y + p.draw_height // 2
            total_len = sum(len(seg.text) for seg in node.label_segments)
            label_col = p.draw_x + (p.draw_width - total_len) // 2
            styled_segs: list[tuple[str, str]] = []
            for seg in node.label_segments:
                if seg.bold:
                    seg_style = "bold_label"
                elif seg.italic:
                    seg_style = "italic_label"
                else:
                    seg_style = "label"
                styled_segs.append((seg.text, seg_style))
            canvas.put_styled_text(label_row, label_col, styled_segs)


def _draw_edges(
    canvas: Canvas, graph: Graph, layout: GridLayout, routed: list[RoutedEdge], cs: CharSet,
    rounded_edges: bool = True,
) -> None:
    """Draw all edge lines, corners, arrows, and labels.

    Labels are drawn in a second pass so they aren't overwritten by
    later edges' line segments.
    """
    # Pass 1a: lines and corners
    for re in routed:
        if len(re.draw_path) < 2:
            continue

        edge = re.edge

        # Resolve per-edge style key
        if re.index in graph.link_styles:
            edge_style_key = f"linkstyle:{re.index}"
        elif -1 in graph.link_styles:
            edge_style_key = f"linkstyle:{re.index}"
        else:
            edge_style_key = "edge"

        # Select line characters based on edge style
        h_char, v_char = _edge_line_chars(edge.style, cs)
        n_segs = len(re.draw_path) - 1

        # Draw line segments, clipping endpoints where arrows are present
        # so the arrow + gap sit between the line and the node border.
        for i in range(n_segs):
            x1, y1 = re.draw_path[i]
            x2, y2 = re.draw_path[i + 1]

            # Clip first segment start if arrow_start
            if i == 0 and edge.has_arrow_start:
                dx = 0 if x2 == x1 else (1 if x2 > x1 else -1)
                dy = 0 if y2 == y1 else (1 if y2 > y1 else -1)
                x1, y1 = x1 + dx, y1 + dy

            # Clip last segment end if arrow_end
            if i == n_segs - 1 and edge.has_arrow_end:
                dx = 0 if x2 == x1 else (1 if x2 > x1 else -1)
                dy = 0 if y2 == y1 else (1 if y2 > y1 else -1)
                x2, y2 = x2 - dx, y2 - dy

            if y1 == y2:
                # Horizontal segment
                canvas.draw_horizontal(y1, x1, x2, h_char, style=edge_style_key)
            elif x1 == x2:
                # Vertical segment
                canvas.draw_vertical(x1, y1, y2, v_char, style=edge_style_key)
            else:
                # Diagonal (shouldn't happen with A*, but handle gracefully)
                _draw_diagonal(canvas, x1, y1, x2, y2, h_char)

        # Draw corners at path turns
        for i in range(1, len(re.draw_path) - 1):
            x_prev, y_prev = re.draw_path[i - 1]
            x_curr, y_curr = re.draw_path[i]
            x_next, y_next = re.draw_path[i + 1]

            corner = _get_corner_char(x_prev, y_prev, x_curr, y_curr, x_next, y_next, cs, rounded=rounded_edges)
            if corner:
                canvas.put(y_curr, x_curr, corner, style=edge_style_key)

    # Pass 1b: arrows and T-junctions (drawn after all lines so they
    # aren't overwritten by later edges' line segments)
    for re in routed:
        if len(re.draw_path) < 2:
            continue

        edge = re.edge

        if re.index in graph.link_styles:
            edge_style_key = f"linkstyle:{re.index}"
        elif -1 in graph.link_styles:
            edge_style_key = f"linkstyle:{re.index}"
        else:
            edge_style_key = "edge"

        arrow_style_key = edge_style_key if edge_style_key != "edge" else "arrow"

        # Draw arrow heads
        if edge.has_arrow_end and len(re.draw_path) >= 2:
            _draw_arrow_head(canvas, re.draw_path[-2], re.draw_path[-1], cs, style=arrow_style_key, arrow_type=edge.arrow_type_end)
        if edge.has_arrow_start and len(re.draw_path) >= 2:
            _draw_arrow_head(canvas, re.draw_path[1], re.draw_path[0], cs, style=arrow_style_key, arrow_type=edge.arrow_type_start)

        # Draw T-junctions where edges leave node borders
        if len(re.draw_path) >= 2:
            if not edge.has_arrow_start:
                _draw_box_start(canvas, re.draw_path[0], re.draw_path[1], re, layout, cs)
            if not edge.has_arrow_end:
                _draw_box_start(canvas, re.draw_path[-1], re.draw_path[-2], re, layout, cs)

    # Pass 2: edge labels (on top of all edge lines)
    placed_labels: list[tuple[int, int, int]] = []  # (row, col_start, col_end)
    for re in routed:
        if re.label and len(re.draw_path) >= 2:
            _draw_edge_label(canvas, re, placed_labels)


def _edge_line_chars(style: EdgeStyle, cs: CharSet) -> tuple[str, str]:
    """Get horizontal and vertical line characters for an edge style."""
    if style == EdgeStyle.DOTTED:
        return cs.line_dotted_h, cs.line_dotted_v
    elif style == EdgeStyle.THICK:
        return cs.line_thick_h, cs.line_thick_v
    elif style == EdgeStyle.INVISIBLE:
        return " ", " "
    return cs.line_horizontal, cs.line_vertical


def _draw_diagonal(
    canvas: Canvas, x1: int, y1: int, x2: int, y2: int, ch: str,
) -> None:
    """Draw a rough diagonal line (fallback)."""
    steps = max(abs(x2 - x1), abs(y2 - y1))
    if steps == 0:
        return
    for step in range(steps + 1):
        x = x1 + (x2 - x1) * step // steps
        y = y1 + (y2 - y1) * step // steps
        canvas.put(y, x, ch)


def _get_corner_char(
    x_prev: int, y_prev: int,
    x_curr: int, y_curr: int,
    x_next: int, y_next: int,
    cs: CharSet,
    rounded: bool = True,
) -> str | None:
    """Determine the corner character at a path turn."""
    # Direction coming in
    dx_in = x_curr - x_prev
    dy_in = y_curr - y_prev

    # Direction going out
    dx_out = x_next - x_curr
    dy_out = y_next - y_curr

    # Normalize to -1/0/1
    dx_in = 0 if dx_in == 0 else (1 if dx_in > 0 else -1)
    dy_in = 0 if dy_in == 0 else (1 if dy_in > 0 else -1)
    dx_out = 0 if dx_out == 0 else (1 if dx_out > 0 else -1)
    dy_out = 0 if dy_out == 0 else (1 if dy_out > 0 else -1)

    if rounded:
        corner_map = {
            (1, 0, 0, 1): cs.round_top_right,       # right then down → ╮
            (1, 0, 0, -1): cs.round_bottom_right,    # right then up → ╯
            (-1, 0, 0, 1): cs.round_top_left,        # left then down → ╭
            (-1, 0, 0, -1): cs.round_bottom_left,    # left then up → ╰
            (0, 1, 1, 0): cs.round_bottom_left,      # down then right → ╰
            (0, 1, -1, 0): cs.round_bottom_right,    # down then left → ╯
            (0, -1, 1, 0): cs.round_top_left,        # up then right → ╭
            (0, -1, -1, 0): cs.round_top_right,      # up then left → ╮
        }
    else:
        corner_map = {
            (1, 0, 0, 1): cs.corner_top_right,      # right then down → ┐
            (1, 0, 0, -1): cs.corner_bottom_right,   # right then up → ┘
            (-1, 0, 0, 1): cs.corner_top_left,       # left then down → ┌
            (-1, 0, 0, -1): cs.corner_bottom_left,   # left then up → └
            (0, 1, 1, 0): cs.corner_bottom_left,     # down then right → └
            (0, 1, -1, 0): cs.corner_bottom_right,   # down then left → ┘
            (0, -1, 1, 0): cs.corner_top_left,       # up then right → ┌
            (0, -1, -1, 0): cs.corner_top_right,     # up then left → ┐
        }

    return corner_map.get((dx_in, dy_in, dx_out, dy_out))


def _draw_arrow_head(
    canvas: Canvas,
    from_point: tuple[int, int],
    to_point: tuple[int, int],
    cs: CharSet,
    style: str = "",
    arrow_type: ArrowType = ArrowType.ARROW,
) -> None:
    """Draw an arrow head one cell before to_point (in the gap, not on the border).

    This prevents the arrow from overwriting shape markers (◆, ◯) on node borders.
    """
    fx, fy = from_point
    tx, ty = to_point

    dx = tx - fx
    dy = ty - fy

    # Normalize direction to -1/0/1
    ndx = 0 if dx == 0 else (1 if dx > 0 else -1)
    ndy = 0 if dy == 0 else (1 if dy > 0 else -1)

    # Place arrow one cell back from the border
    ax = tx - ndx
    ay = ty - ndy

    if arrow_type == ArrowType.CIRCLE:
        canvas.put(ay, ax, cs.circle_endpoint, style=style)
    elif arrow_type == ArrowType.CROSS:
        canvas.put(ay, ax, cs.cross_endpoint, style=style)
    elif ndx > 0:
        canvas.put(ay, ax, cs.arrow_right, style=style)
    elif ndx < 0:
        canvas.put(ay, ax, cs.arrow_left, style=style)
    elif ndy > 0:
        canvas.put(ay, ax, cs.arrow_down, style=style)
    elif ndy < 0:
        canvas.put(ay, ax, cs.arrow_up, style=style)


def _draw_box_start(
    canvas: Canvas,
    edge_point: tuple[int, int],
    next_point: tuple[int, int],
    re: RoutedEdge,
    layout: GridLayout,
    cs: CharSet,
) -> None:
    """Draw a T-junction where an edge leaves a node border."""
    ex, ey = edge_point
    nx, ny = next_point

    dx = nx - ex
    dy = ny - ey

    if dx > 0:
        tee = cs.tee_right if cs.horizontal == "─" else "+"
    elif dx < 0:
        tee = cs.tee_left if cs.horizontal == "─" else "+"
    elif dy > 0:
        tee = cs.tee_down if cs.horizontal == "─" else "+"
    elif dy < 0:
        tee = cs.tee_up if cs.horizontal == "─" else "+"
    else:
        return

    canvas.put(ey, ex, tee)


def _label_overlaps(
    row: int, col_start: int, col_end: int,
    placed: list[tuple[int, int, int]],
) -> bool:
    """Check if a label placement overlaps any already-placed label."""
    for pr, ps, pe in placed:
        if pr == row and col_start < pe and col_end > ps:
            return True
    return False


def _try_place_label(
    canvas: Canvas,
    row: int, col: int, label: str,
    placed: list[tuple[int, int, int]],
) -> bool:
    """Try to place a label at (row, col). Returns True if placed."""
    col_end = col + len(label)
    if col < 0 or row < 0:
        return False
    if _label_overlaps(row, col, col_end, placed):
        return False
    # Ensure canvas is large enough for the label
    needed_w = col_end + 1
    needed_h = row + 1
    if needed_w > canvas.width or needed_h > canvas.height:
        canvas.resize(max(canvas.width, needed_w), max(canvas.height, needed_h))
    canvas.put_text(row, col, label, style="edge_label")
    placed.append((row, col, col_end))
    return True


def _find_last_turn(path: list[tuple[int, int]]) -> int:
    """Find the index of the last turn in a path. Returns -1 if no turns."""
    for i in range(len(path) - 2, 0, -1):
        x_prev, y_prev = path[i - 1]
        x_curr, y_curr = path[i]
        x_next, y_next = path[i + 1]
        # Direction changes at this point
        dx_in = x_curr - x_prev
        dy_in = y_curr - y_prev
        dx_out = x_next - x_curr
        dy_out = y_next - y_curr
        if (dx_in, dy_in) != (0, 0) and (dx_out, dy_out) != (0, 0):
            # Normalize
            dx_in = 0 if dx_in == 0 else (1 if dx_in > 0 else -1)
            dy_in = 0 if dy_in == 0 else (1 if dy_in > 0 else -1)
            dx_out = 0 if dx_out == 0 else (1 if dx_out > 0 else -1)
            dy_out = 0 if dy_out == 0 else (1 if dy_out > 0 else -1)
            if (dx_in, dy_in) != (dx_out, dy_out):
                return i
    return -1


def _try_place_on_segment(
    canvas: Canvas, x1: int, y1: int, x2: int, y2: int,
    label: str, placed_labels: list[tuple[int, int, int]],
    prev_point: tuple[int, int] | None = None,
    prefer_left: bool = False,
    bias_target: bool = False,
) -> bool:
    """Try to place a label on a specific segment. Returns True if placed.

    prev_point: the path point before (x1, y1), used to determine which side
    of a vertical segment to prefer after a horizontal turn.
    prefer_left: explicitly prefer the left side for vertical segments.
    bias_target: place closer to the target end (2/3) instead of midpoint.
    """
    label_len = len(label)

    if x1 == x2 and abs(y2 - y1) >= 2:
        # Vertical segment — place beside the line.
        # If preceded by a horizontal turn, prefer the inner side
        # (left if turn came from the right, right if from the left).
        lo, hi = min(y1, y2), max(y1, y2)
        if bias_target:
            # Place 2/3 toward the target end (y2)
            if y2 > y1:
                mid_y = y1 + (y2 - y1) * 2 // 3
            else:
                mid_y = y1 + (y2 - y1) * 2 // 3
        else:
            mid_y = (lo + hi) // 2

        if not prefer_left and prev_point is not None:
            px, py = prev_point
            if py == y1 and px != x1:
                # Horizontal predecessor — turn came from left (px < x1) or right (px > x1)
                # Place label on the side the turn came from (inner side of the branch)
                prefer_left = px > x1  # came from right → prefer left

        if prefer_left:
            sides = [
                (mid_y, x1 - label_len),       # left
                (mid_y, x1 + 1),                # right
            ]
        else:
            sides = [
                (mid_y, x1 + 1),                # right
                (mid_y, x1 - label_len),        # left
            ]

        for row, col in sides:
            if _try_place_label(canvas, row, col, label, placed_labels):
                return True
        for offset in range(1, 4):
            for row, col in sides:
                if _try_place_label(canvas, row - offset, col, label, placed_labels):
                    return True
                if _try_place_label(canvas, row + offset, col, label, placed_labels):
                    return True
        return False

    if y1 == y2:
        # Horizontal segment — center label above/below
        seg_len = abs(x2 - x1)
        if seg_len >= label_len + 2:
            mid = (min(x1, x2) + max(x1, x2)) // 2
            start = mid - label_len // 2
            if _try_place_label(canvas, y1 - 1, start, label, placed_labels):
                return True
            if _try_place_label(canvas, y1 + 1, start, label, placed_labels):
                return True
            return False

    return False


def _draw_edge_label(
    canvas: Canvas, re: RoutedEdge,
    placed_labels: list[tuple[int, int, int]],
) -> None:
    """Draw an edge label on the best segment of the path.

    Prefers segments after the last turn (the unique part of the edge path)
    so labels appear on the branch, not on a shared trunk.
    Uses collision detection to avoid overlapping previously placed labels.
    """
    label = re.label
    if not label:
        return

    label_len = len(label)
    path = re.draw_path

    # Build segment list ordered by preference: post-turn segments first,
    # then remaining segments in reverse order (end segments are more unique)
    n_segs = len(path) - 1
    if n_segs <= 0:
        return

    last_turn = _find_last_turn(path)
    preferred: list[int] = []
    remaining: list[int] = []

    if last_turn >= 0:
        # Segments after the last turn (unique to this edge)
        for i in range(last_turn, n_segs):
            preferred.append(i)
        # Then remaining segments in reverse
        for i in range(last_turn - 1, -1, -1):
            remaining.append(i)
    else:
        # No turns — straight path, use all segments
        for i in range(n_segs):
            remaining.append(i)

    # For straight paths (no turns), prefer left side and bias toward target
    # so the label doesn't land on the same row as sibling edges' turns
    is_straight = last_turn < 0

    # Try preferred segments first, then remaining
    for i in preferred + remaining:
        x1, y1 = path[i]
        x2, y2 = path[i + 1]
        prev = path[i - 1] if i > 0 else None
        if _try_place_on_segment(
            canvas, x1, y1, x2, y2, label, placed_labels,
            prev_point=prev,
            prefer_left=is_straight,
            bias_target=is_straight,
        ):
            return

    # Force place at midpoint of path
    mid_idx = len(path) // 2
    mx, my = path[mid_idx]
    canvas.put_text(my - 1, mx + 1, label, style="edge_label")
    placed_labels.append((my - 1, mx + 1, mx + 1 + label_len))


def _draw_notes(canvas: Canvas, graph: Graph, layout: GridLayout, cs: CharSet) -> None:
    """Draw note boxes next to their target nodes."""
    for note in graph.notes:
        if note.target not in layout.placements:
            continue
        p = layout.placements[note.target]

        lines = note.text.split("\n")
        note_width = max(len(line) for line in lines) + 4
        note_height = len(lines) + 2

        if note.position == "rightof":
            note_x = p.draw_x + p.draw_width + 2
        else:  # leftof
            note_x = p.draw_x - note_width - 2
            note_x = max(0, note_x)

        note_y = p.draw_y + (p.draw_height - note_height) // 2

        # Extend canvas if needed
        needed_w = note_x + note_width + 2
        needed_h = note_y + note_height + 2
        if needed_w > canvas.width or needed_h > canvas.height:
            canvas.resize(max(canvas.width, needed_w), max(canvas.height, needed_h))

        draw_rectangle(canvas, note_x, note_y, note_width, note_height, note.text, cs, style="node")
