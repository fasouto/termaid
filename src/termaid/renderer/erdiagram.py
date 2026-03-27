"""Renderer for ER diagrams.

Renders an ERDiagram directly to a Canvas using layered layout,
following the same pattern as the class diagram renderer.
"""
from __future__ import annotations

from collections import deque

from ..model.erdiagram import Entity, ERDiagram, Relationship
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from ..utils import display_width

# ── layout constants ──────────────────────────────────────────────
_PAD = 2             # horizontal padding inside entity box
_MIN_BOX_WIDTH = 16  # minimum entity box width
_LAYER_GAP = 4       # gap between layers
_SIBLING_GAP = 4     # gap between entities in same layer
_MARGIN = 2          # canvas margin


def _card_text(card: str) -> str:
    """Convert cardinality marker to display text."""
    # Normalize: treat left and right markers uniformly
    # Left:  || |o }| }o
    # Right: || o| |{ o{
    s = set(card)
    if s == {"|"}:
        return "1"
    if "o" in s and "}" not in s and "{" not in s:
        return "0..1"
    if ("}" in s or "{" in s) and "o" not in s:
        return "1..*"
    if ("}" in s or "{" in s) and "o" in s:
        return "0..*"
    return card


def _format_attribute(attr) -> str:
    """Format an attribute for display."""
    parts = [attr.type, " ", attr.name]
    if attr.keys:
        parts.append("  ")
        parts.append(",".join(attr.keys))
    if attr.comment:
        parts.append("  ")
        parts.append('"' + attr.comment + '"')
    return "".join(parts)


def _compute_box_size(entity: Entity, padding_x: int = _PAD) -> tuple[int, int]:
    """Compute (width, height) for an entity box."""
    lines: list[str] = [entity.display_name]

    attr_lines: list[str] = []
    for attr in entity.attributes:
        attr_lines.append(_format_attribute(attr))

    all_lines = lines + attr_lines
    max_text = max((len(l) for l in all_lines), default=0)
    width = max(max_text + padding_x * 2, _MIN_BOX_WIDTH)

    # Height: top border + name row + [divider + attr rows] + bottom border
    height = 2 + len(lines)  # borders + name
    if attr_lines:
        height += 1 + len(attr_lines)  # divider + attributes

    return width, height


def _draw_entity_box(
    canvas: Canvas, x: int, y: int, entity: Entity, cs: CharSet,
    padding_x: int = _PAD,
) -> tuple[int, int]:
    """Draw an entity box and return (width, height)."""
    width, height = _compute_box_size(entity, padding_x=padding_x)
    style = "node"

    # Top border
    canvas.put(y, x, cs.top_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, cs.top_right, style=style)

    # Bottom border
    canvas.put(y + height - 1, x, cs.bottom_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, cs.bottom_right, style=style)

    # Side borders
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    # Name (centered)
    row = y + 1
    name = entity.display_name
    name_col = x + (width - len(name)) // 2
    canvas.put_text(row, name_col, name, style="label")
    row += 1

    # Attributes
    if entity.attributes:
        # Divider
        canvas.put(row, x, cs.tee_right, style=style)
        for c in range(x + 1, x + width - 1):
            canvas.put(row, c, cs.horizontal, style=style)
        canvas.put(row, x + width - 1, cs.tee_left, style=style)
        row += 1

        for attr in entity.attributes:
            text = _format_attribute(attr)
            canvas.put_text(row, x + padding_x, text, style="label")
            row += 1

    return width, height


def _assign_layers(diagram: ERDiagram) -> list[list[str]]:
    """Assign entities to layers using BFS."""
    entity_names = list(diagram.entities.keys())
    if not entity_names:
        return []

    # Build adjacency: entity1 → entity2 for all relationships
    children: dict[str, list[str]] = {n: [] for n in entity_names}
    has_parent: set[str] = set()

    for rel in diagram.relationships:
        if rel.entity1 in children:
            children[rel.entity1].append(rel.entity2)
        has_parent.add(rel.entity2)

    # BFS from roots
    roots = [n for n in entity_names if n not in has_parent]
    if not roots:
        roots = [entity_names[0]]

    assigned: set[str] = set()
    layers: list[list[str]] = []
    queue = deque(roots)
    for r in roots:
        assigned.add(r)

    while queue:
        layer: list[str] = []
        for _ in range(len(queue)):
            node = queue.popleft()
            layer.append(node)
        layers.append(layer)

        next_queue: list[str] = []
        for node in layer:
            for child in children.get(node, []):
                if child not in assigned:
                    assigned.add(child)
                    next_queue.append(child)
        queue.extend(next_queue)

    # Add disconnected entities
    disconnected = [n for n in entity_names if n not in assigned]
    if disconnected:
        layers.append(disconnected)

    return layers


def _compute_layout(
    diagram: ERDiagram,
    padding_x: int = _PAD,
    gap: int = _SIBLING_GAP,
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]], int, int, dict[str, int]]:
    """Compute positions and sizes for all entities.

    Returns (positions, sizes, canvas_width, canvas_height, layer_of).
    """
    layers = _assign_layers(diagram)
    if not layers:
        return {}, {}, 1, 1, {}

    sizes: dict[str, tuple[int, int]] = {}
    for name, entity in diagram.entities.items():
        sizes[name] = _compute_box_size(entity, padding_x=padding_x)

    layer_of: dict[str, int] = {}
    for li, layer in enumerate(layers):
        for name in layer:
            layer_of[name] = li

    # Compute per-pair gaps for same-layer relationship labels
    pair_gap: dict[tuple[str, str], int] = {}
    for rel in diagram.relationships:
        s, t = rel.entity1, rel.entity2
        if s in layer_of and t in layer_of and layer_of[s] == layer_of[t]:
            pair_g = display_width(rel.label) + 4 if rel.label else gap
            pair_g = max(pair_g, gap)
            key = (min(s, t), max(s, t))
            pair_gap[key] = max(pair_gap.get(key, gap), pair_g)

    # Compute cross-layer gap needed for LR mode (labels + cardinality between columns)
    cross_layer_gap = gap
    for rel in diagram.relationships:
        s, t = rel.entity1, rel.entity2
        if s in layer_of and t in layer_of and layer_of[s] != layer_of[t]:
            needed = 4  # base gap for line
            card1_len = len(_card_text(rel.card1))
            card2_len = len(_card_text(rel.card2))
            needed = max(needed, card1_len + card2_len + 4)
            if rel.label:
                needed = max(needed, display_width(rel.label) + 4)
            cross_layer_gap = max(cross_layer_gap, needed)

    is_lr = diagram.direction == "LR"

    if is_lr:
        positions: dict[str, tuple[int, int]] = {}
        col_x = _MARGIN
        max_height = 0

        for layer in layers:
            layer_width = max(sizes[n][0] for n in layer)
            row_y = _MARGIN

            for name in layer:
                w, h = sizes[name]
                x_offset = (layer_width - w) // 2
                positions[name] = (col_x + x_offset, row_y)
                row_y += h + gap

            total_layer_height = row_y - gap + _MARGIN
            max_height = max(max_height, total_layer_height)
            col_x += layer_width + cross_layer_gap

        canvas_width = col_x - gap + _MARGIN
        canvas_height = max_height
    else:
        positions = {}
        row_y = _MARGIN
        max_width = 0

        for layer in layers:
            layer_height = max(sizes[n][1] for n in layer)

            col_x = _MARGIN
            for idx, name in enumerate(layer):
                w, h = sizes[name]
                y_offset = (layer_height - h) // 2
                positions[name] = (col_x, row_y + y_offset)
                if idx < len(layer) - 1:
                    next_name = layer[idx + 1]
                    key = (min(name, next_name), max(name, next_name))
                    pair_g = pair_gap.get(key, gap)
                    col_x += w + pair_g
                else:
                    col_x += w

            max_width = max(max_width, col_x + _MARGIN)
            row_y += layer_height + gap

        canvas_width = max_width
        canvas_height = row_y - gap + _MARGIN

    # Center each layer
    if is_lr:
        for layer in layers:
            layer_h = sum(sizes[n][1] for n in layer) + gap * (len(layer) - 1)
            offset = (canvas_height - 2 * _MARGIN - layer_h) // 2
            if offset > 0:
                for name in layer:
                    x, y = positions[name]
                    positions[name] = (x, y + offset)
    else:
        for layer in layers:
            # Compute actual layer width from positions
            min_x = min(positions[n][0] for n in layer)
            max_x = max(positions[n][0] + sizes[n][0] for n in layer)
            layer_w = max_x - min_x
            offset = (canvas_width - 2 * _MARGIN - layer_w) // 2
            if offset > 0:
                for name in layer:
                    x, y = positions[name]
                    positions[name] = (x + offset, y)

    return positions, sizes, canvas_width, canvas_height, layer_of


def _draw_routed_line(
    canvas: Canvas,
    r1: int, c1: int, r2: int, c2: int,
    h_char: str, v_char: str, use_ascii: bool,
    style: str = "edge",
) -> None:
    """Draw a routed line from (r1,c1) to (r2,c2)."""
    if c1 == c2:
        for r in range(min(r1, r2), max(r1, r2) + 1):
            canvas.put(r, c1, v_char, style=style)
    elif r1 == r2:
        for c in range(min(c1, c2), max(c1, c2) + 1):
            canvas.put(r1, c, h_char, style=style)
    else:
        mid_row = (r1 + r2) // 2
        for r in range(min(r1, mid_row), max(r1, mid_row) + 1):
            canvas.put(r, c1, v_char, style=style)
        for c in range(min(c1, c2), max(c1, c2) + 1):
            canvas.put(mid_row, c, h_char, style=style)
        for r in range(min(mid_row, r2), max(mid_row, r2) + 1):
            canvas.put(r, c2, v_char, style=style)
        if not use_ascii:
            if r1 < mid_row:
                corner1 = "┘" if c2 < c1 else "└"
            else:
                corner1 = "┐" if c2 < c1 else "┌"
            canvas.put(mid_row, c1, corner1, style=style)
            if r2 > mid_row:
                corner2 = "┌" if c2 < c1 else "┐"
            else:
                corner2 = "└" if c2 < c1 else "┘"
            canvas.put(mid_row, c2, corner2, style=style)


def _draw_relationship(
    canvas: Canvas,
    rel: Relationship,
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
    layer_of: dict[str, int],
    cs: CharSet,
    use_ascii: bool,
    src_col_offset: int = 0,
    is_lr: bool = False,
) -> None:
    """Draw a relationship line between two entities with cardinality."""
    if rel.entity1 not in positions or rel.entity2 not in positions:
        return

    sx, sy = positions[rel.entity1]
    sw, sh = sizes[rel.entity1]
    tx, ty = positions[rel.entity2]
    tw, th = sizes[rel.entity2]

    s_cx = sx + sw // 2
    s_cy = sy + sh // 2
    t_cx = tx + tw // 2
    t_cy = ty + th // 2

    # Use layer info to decide connection mode
    s_layer = layer_of.get(rel.entity1, -1)
    t_layer = layer_of.get(rel.entity2, -2)
    same_layer = s_layer == t_layer

    if is_lr:
        use_horizontal = not same_layer
    else:
        use_horizontal = same_layer

    if not use_horizontal:
        dy = t_cy - s_cy
        if dy > 0:
            start_col = s_cx + src_col_offset
            start_row = sy + sh
            end_col = t_cx
            end_row = ty - 1
        else:
            start_col = s_cx + src_col_offset
            start_row = sy - 1
            end_col = t_cx
            end_row = ty + th
    else:
        dx = t_cx - s_cx
        if dx > 0:
            start_col = sx + sw
            start_row = s_cy
            end_col = tx - 1
            end_row = t_cy
        else:
            start_col = sx - 1
            start_row = s_cy
            end_col = tx + tw
            end_row = t_cy

    h_char = cs.line_dotted_h if rel.line_style == "dashed" else cs.line_horizontal
    v_char = cs.line_dotted_v if rel.line_style == "dashed" else cs.line_vertical
    style = "edge"

    _draw_routed_line(canvas, start_row, start_col, end_row, end_col,
                      h_char, v_char, use_ascii, style)

    # Draw cardinality text near endpoints
    card1_text = _card_text(rel.card1)
    card2_text = _card_text(rel.card2)

    if use_horizontal:
        # Horizontal connection: cardinality above the line near endpoints
        if card1_text:
            canvas.put_text(start_row - 1, start_col + 1, card1_text, style="edge_label")
        if card2_text:
            canvas.put_text(end_row - 1, end_col - display_width(card2_text), card2_text, style="edge_label")
    else:
        # Vertical connection: cardinality to the right of endpoint
        if card1_text:
            canvas.put_text(start_row, start_col + 1, card1_text, style="edge_label")
        if card2_text:
            canvas.put_text(end_row, end_col + 1, card2_text, style="edge_label")

    # Draw label
    if rel.label:
        if start_row == end_row:
            # Horizontal: label below the line, centered
            mid_c = (start_col + end_col) // 2
            label_col = mid_c - display_width(rel.label) // 2
            canvas.put_text(start_row + 1, label_col, rel.label, style="edge_label")
        elif start_col == end_col:
            # Straight vertical: label to the right of midpoint
            mid_r = (start_row + end_row) // 2
            canvas.put_text(mid_r, start_col + 2, rel.label, style="edge_label")
        else:
            # Z-shaped: place label on second segment
            mid_r = (start_row + end_row) // 2
            if use_horizontal:
                # Label below the horizontal bend
                label_r = mid_r + 1
                label_c = (start_col + end_col) // 2 - display_width(rel.label) // 2
                canvas.put_text(label_r, label_c, rel.label, style="edge_label")
            else:
                # Label to the right of first vertical segment (near source)
                label_r = start_row + (mid_r - start_row) // 2
                if label_r == start_row:
                    label_r = start_row + 1
                canvas.put_text(label_r, start_col + 2, rel.label, style="edge_label")


def _compute_exit_offsets(
    diagram: ERDiagram,
    layer_of: dict[str, int],
) -> dict[int, int]:
    """Compute horizontal offset for each relationship's exit point."""
    groups: dict[tuple[str, str], list[int]] = {}
    for i, rel in enumerate(diagram.relationships):
        s_layer = layer_of.get(rel.entity1, -1)
        t_layer = layer_of.get(rel.entity2, -2)
        same_layer = s_layer == t_layer
        side = "side" if same_layer else "bottom"
        key = (rel.entity1, side)
        groups.setdefault(key, []).append(i)

    offsets: dict[int, int] = {}
    for _key, indices in groups.items():
        if len(indices) <= 1:
            for idx in indices:
                offsets[idx] = 0
            continue
        n = len(indices)
        for j, idx in enumerate(indices):
            offsets[idx] = (j - (n - 1) / 2) * 3
    return offsets


def render_er_diagram(diagram: ERDiagram, *, use_ascii: bool = False, padding_x: int = 2, gap: int = 4) -> Canvas:
    """Render an ERDiagram to a Canvas."""
    cs = ASCII if use_ascii else UNICODE

    positions, sizes, width, height, layer_of = _compute_layout(diagram, padding_x=padding_x, gap=gap)
    if width <= 1:
        return Canvas(1, 1)

    # Expand canvas to fit relationship labels and cardinality text
    for rel in diagram.relationships:
        if rel.entity1 not in positions or rel.entity2 not in positions:
            continue
        sx, sy = positions[rel.entity1]
        sw, _ = sizes[rel.entity1]
        tx, ty = positions[rel.entity2]
        tw, _ = sizes[rel.entity2]
        mid_c = (sx + sw // 2 + tx + tw // 2) // 2
        if rel.label:
            label_end = mid_c + 2 + display_width(rel.label)
            width = max(width, label_end + _MARGIN)
        # Cardinality text at endpoints
        for card in (rel.card1, rel.card2):
            card_len = len(_card_text(card))
            width = max(width, mid_c + 1 + card_len + _MARGIN)

    exit_offsets = _compute_exit_offsets(diagram, layer_of)

    canvas = Canvas(width, height)

    # Draw relationships first (background)
    for i, rel in enumerate(diagram.relationships):
        col_offset = int(exit_offsets.get(i, 0))
        _draw_relationship(canvas, rel, positions, sizes, layer_of, cs, use_ascii,
                           src_col_offset=col_offset, is_lr=diagram.direction == "LR")

    # Draw entity boxes on top
    for name, entity in diagram.entities.items():
        if name in positions:
            x, y = positions[name]
            _draw_entity_box(canvas, x, y, entity, cs, padding_x=padding_x)

    return canvas
