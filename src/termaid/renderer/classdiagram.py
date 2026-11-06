"""Renderer for class diagrams.

Renders a ClassDiagram directly to a Canvas using layered layout,
following the same pattern as the sequence diagram renderer.
"""
from __future__ import annotations

from collections import deque

from ..model.classdiagram import ClassDef, ClassDiagram, Note, Relationship
from .canvas import Canvas
from .charset import ASCII, CharSet, default_charset
from .relation_tracks import assign_tracks
from ..utils import display_width

# ── layout constants ──────────────────────────────────────────────
_CLASS_PAD = 2       # horizontal padding inside class box
_MIN_BOX_WIDTH = 16  # minimum class box width
_LAYER_GAP = 4       # gap between layers (for routing)
_SIBLING_GAP = 4     # gap between classes in same layer
_MARGIN = 2          # canvas margin


def _format_member(member) -> str:
    """Format a member for display."""
    parts: list[str] = []
    if member.visibility:
        parts.append(member.visibility)
    if member.return_type and not member.is_method:
        parts.append(member.return_type + " ")
    parts.append(member.name)
    if member.is_method and member.return_type:
        parts.append(" " + member.return_type)
    if member.classifier:
        parts.append(member.classifier)
    return "".join(parts)


def _compute_box_size(cls: ClassDef, padding_x: int = _CLASS_PAD) -> tuple[int, int]:
    """Compute (width, height) for a class box."""
    # Annotation line
    lines: list[str] = []
    if cls.annotation:
        lines.append(f"\u00ab{cls.annotation}\u00bb")
    lines.append(cls.name)

    attributes = [m for m in cls.members if not m.is_method]
    methods = [m for m in cls.members if m.is_method]

    member_lines: list[str] = []
    for m in attributes:
        member_lines.append(_format_member(m))
    for m in methods:
        member_lines.append(_format_member(m))

    all_lines = lines + member_lines
    max_text = max((display_width(l) for l in all_lines), default=0)
    width = max(max_text + padding_x * 2, _MIN_BOX_WIDTH)

    # Height: top border + name rows + dividers + member rows + bottom border
    height = 2  # top + bottom borders
    height += len(lines)  # name/annotation rows

    has_attrs = len(attributes) > 0
    has_methods = len(methods) > 0

    if has_attrs or has_methods:
        height += 1  # divider after name
        height += len(attributes)
        if has_attrs and has_methods:
            height += 1  # divider between attrs and methods
        height += len(methods)

    return width, height


def _draw_class_box(
    canvas: Canvas, x: int, y: int, cls: ClassDef, cs: CharSet,
    padding_x: int = _CLASS_PAD,
) -> tuple[int, int]:
    """Draw a class box and return (width, height)."""
    width, height = _compute_box_size(cls, padding_x=padding_x)
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

    # Name section
    row = y + 1
    if cls.annotation:
        ann_text = f"\u00ab{cls.annotation}\u00bb"
        ann_col = x + (width - display_width(ann_text)) // 2
        canvas.put_text(row, ann_col, ann_text, style="label")
        row += 1

    name_col = x + (width - display_width(cls.name)) // 2
    canvas.put_text(row, name_col, cls.name, style="label")
    row += 1

    attributes = [m for m in cls.members if not m.is_method]
    methods = [m for m in cls.members if m.is_method]

    has_attrs = len(attributes) > 0
    has_methods = len(methods) > 0

    if has_attrs or has_methods:
        # Divider after name
        canvas.put(row, x, cs.tee_right, style=style)
        for c in range(x + 1, x + width - 1):
            canvas.put(row, c, cs.horizontal, style=style)
        canvas.put(row, x + width - 1, cs.tee_left, style=style)
        row += 1

        # Attributes
        for m in attributes:
            text = _format_member(m)
            canvas.put_text(row, x + padding_x, text, style="label")
            row += 1

        if has_attrs and has_methods:
            # Divider between attributes and methods
            canvas.put(row, x, cs.tee_right, style=style)
            for c in range(x + 1, x + width - 1):
                canvas.put(row, c, cs.horizontal, style=style)
            canvas.put(row, x + width - 1, cs.tee_left, style=style)
            row += 1

        # Methods
        for m in methods:
            text = _format_member(m)
            canvas.put_text(row, x + padding_x, text, style="label")
            row += 1

    return width, height


def _assign_layers(diagram: ClassDiagram) -> list[list[str]]:
    """Assign classes to layers using BFS from root classes."""
    class_names = list(diagram.classes.keys())
    if not class_names:
        return []

    # Build adjacency: parent → children for BFS layering.
    # The marker points AT the parent class:
    #   "Animal <|-- Duck" → source=Animal, source_marker="<|" → Animal is parent
    #   "Duck --|> Animal" → target=Animal, target_marker="|>" → Animal is parent
    children: dict[str, list[str]] = {n: [] for n in class_names}
    has_parent: set[str] = set()

    for rel in diagram.relationships:
        if rel.source_marker == "<|" or rel.target_marker == "|>":
            parent = rel.source if rel.source_marker == "<|" else rel.target
            child = rel.target if rel.source_marker == "<|" else rel.source
            if parent in children:
                children[parent].append(child)
            has_parent.add(child)
        else:
            # Other relationships: source -> target
            if rel.source in children:
                children[rel.source].append(rel.target)
            has_parent.add(rel.target)

    # BFS from roots (classes with no incoming parent-like edges)
    roots = [n for n in class_names if n not in has_parent]
    if not roots:
        roots = [class_names[0]]

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

    # Add any disconnected classes
    disconnected = [n for n in class_names if n not in assigned]
    if disconnected:
        layers.append(disconnected)

    return layers


def _compute_layout(
    diagram: ClassDiagram,
    padding_x: int = _CLASS_PAD,
    gap: int = _SIBLING_GAP,
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]], int, int, dict[str, int], dict[int, int]]:
    """Compute positions and sizes for all classes.

    Returns (positions, sizes, canvas_width, canvas_height, layer_of).
    positions: {class_name: (x, y)}
    sizes: {class_name: (width, height)}
    layer_of: {class_name: layer_index}
    """
    layers = _assign_layers(diagram)
    if not layers:
        return {}, {}, 1, 1, {}, {}

    # Compute box sizes
    sizes: dict[str, tuple[int, int]] = {}
    for name, cls in diagram.classes.items():
        sizes[name] = _compute_box_size(cls, padding_x=padding_x)

    # Build set of class names in each layer for gap computation
    layer_of: dict[str, int] = {}
    for li, layer in enumerate(layers):
        for name in layer:
            layer_of[name] = li

    # Compute per-pair gaps needed for horizontal relationship labels
    # between classes in the same layer
    pair_gap: dict[tuple[str, str], int] = {}
    for rel in diagram.relationships:
        s, t = rel.source, rel.target
        if s in layer_of and t in layer_of and layer_of[s] == layer_of[t]:
            pair_g = display_width(rel.label) + 4 if rel.label else gap
            pair_g = max(pair_g, gap)
            key = (min(s, t), max(s, t))
            pair_gap[key] = max(pair_gap.get(key, gap), pair_g)

    is_lr = diagram.direction == "LR"
    run_rows: dict[int, int] = {}

    if is_lr:
        # Layers are columns, classes stacked vertically
        positions: dict[str, tuple[int, int]] = {}
        col_x = _MARGIN
        max_height = 0

        for layer in layers:
            layer_width = max(sizes[n][0] for n in layer)
            row_y = _MARGIN

            for name in layer:
                w, h = sizes[name]
                # Center horizontally within column
                x_offset = (layer_width - w) // 2
                positions[name] = (col_x + x_offset, row_y)
                row_y += h + gap

            total_layer_height = row_y - gap + _MARGIN
            max_height = max(max_height, total_layer_height)
            col_x += layer_width + gap

        canvas_width = col_x - gap + _MARGIN
        canvas_height = max_height
    else:
        # TB: layers are rows, boxes placed horizontally.
        # Columns first, since they do not depend on the vertical gaps.
        positions = {}
        layer_heights: list[int] = []
        max_width = 0

        for layer in layers:
            layer_heights.append(max(sizes[n][1] for n in layer))
            col_x = _MARGIN
            for idx, name in enumerate(layer):
                w, _ = sizes[name]
                positions[name] = (col_x, 0)
                if idx < len(layer) - 1:
                    next_name = layer[idx + 1]
                    key = (min(name, next_name), max(name, next_name))
                    col_x += w + pair_gap.get(key, gap)
                else:
                    col_x += w
            max_width = max(max_width, col_x + _MARGIN)
        canvas_width = max_width

        # Center each layer horizontally
        for layer in layers:
            min_x = min(positions[n][0] for n in layer)
            max_x = max(positions[n][0] + sizes[n][0] for n in layer)
            offset = (canvas_width - 2 * _MARGIN - (max_x - min_x)) // 2
            if offset > 0:
                for name in layer:
                    positions[name] = (positions[name][0] + offset, 0)

        # Rows: the gap below a layer grows to hold one track per relationship
        # that jogs sideways inside it, so their runs never share a row.
        tracks, gap_heights = _assign_gap_tracks(diagram, layer_of, positions, sizes)
        layer_tops: list[int] = []
        row_y = _MARGIN
        for li, layer in enumerate(layers):
            layer_tops.append(row_y)
            layer_height = layer_heights[li]
            for name in layer:
                x, _ = positions[name]
                _, h = sizes[name]
                positions[name] = (x, row_y + (layer_height - h) // 2)
            row_y += layer_height + max(gap, gap_heights.get(li, 0) + 2)
        canvas_height = layer_tops[-1] + layer_heights[-1] + _MARGIN

        for index, (boundary, offset) in tracks.items():
            run_rows[index] = layer_tops[boundary] + layer_heights[boundary] + offset

    if is_lr:
        # Center each column vertically
        for layer in layers:
            layer_h = sum(sizes[n][1] for n in layer) + gap * (len(layer) - 1)
            offset = (canvas_height - 2 * _MARGIN - layer_h) // 2
            if offset > 0:
                for name in layer:
                    x, y = positions[name]
                    positions[name] = (x, y + offset)

    return positions, sizes, canvas_width, canvas_height, layer_of, run_rows


def _assign_gap_tracks(
    diagram: ClassDiagram,
    layer_of: dict[str, int],
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
) -> tuple[dict[int, tuple[int, int]], dict[int, int]]:
    """Give every sideways run between adjacent layers its own row.

    Returns ({rel_index: (upper_layer_index, row_offset)}, {layer: rows}):
    the offset counts rows below the upper layer's bottom border, and the
    second map says how many rows each gap needs for its runs. A run whose
    label does not fit between its corners gets a second row so the label
    can hang below it. Runs that skip a layer or drop straight down keep the
    default routing and are not listed.
    """
    exit_offsets = _compute_exit_offsets(diagram, layer_of)
    entry_offsets = _compute_exit_offsets(diagram, layer_of, end="target")
    intervals: dict[int, dict[int, tuple[int, int]]] = {}
    hanging: dict[int, bool] = {}
    for i, rel in enumerate(diagram.relationships):
        src, tgt = rel.source, rel.target
        if src not in positions or tgt not in positions:
            continue
        ls, lt = layer_of.get(src, -1), layer_of.get(tgt, -2)
        if abs(ls - lt) != 1:
            continue
        start_col = positions[src][0] + sizes[src][0] // 2 + int(exit_offsets.get(i, 0))
        end_col = positions[tgt][0] + sizes[tgt][0] // 2 + int(entry_offsets.get(i, 0))
        if start_col == end_col:
            continue
        boundary = min(ls, lt)
        left, right = min(start_col, end_col), max(start_col, end_col)
        label_width = display_width(rel.label) if rel.label else 0
        hanging[i] = bool(label_width) and right - left - 2 < label_width
        if hanging[i]:
            # The label will hang below the run, to the right of the drop
            # into the target; keep that span clear on the same track too.
            right = max(right, end_col + 2 + label_width)
        intervals.setdefault(boundary, {})[i] = (left, right)

    rows: dict[int, tuple[int, int]] = {}
    gap_heights: dict[int, int] = {}
    for boundary, runs in intervals.items():
        tracks = assign_tracks(runs)
        heights = [1] * (max(tracks.values()) + 1)
        for index, track in tracks.items():
            if hanging[index]:
                heights[track] = 2
        offsets = [1]
        for height in heights:
            offsets.append(offsets[-1] + height)
        for index, track in tracks.items():
            rows[index] = (boundary, offsets[track])
        gap_heights[boundary] = offsets[-1] - 1
    return rows, gap_heights


def _draw_routed_line(
    canvas: Canvas,
    r1: int, c1: int, r2: int, c2: int,
    h_char: str, v_char: str, use_ascii: bool,
    style: str = "edge",
    mid_row: int | None = None,
) -> None:
    """Draw a routed line from (r1,c1) to (r2,c2).

    Routing strategy:
    - Straight if aligned on one axis
    - Otherwise: vertical from start, horizontal bend, vertical to end
    """
    # Spread exit and entry points can push a line past the rightmost box
    canvas.resize(max(c1, c2) + 1, canvas.height)
    if c1 == c2:
        # Straight vertical
        for r in range(min(r1, r2), max(r1, r2) + 1):
            canvas.put(r, c1, v_char, style=style)
    elif r1 == r2:
        # Straight horizontal
        for c in range(min(c1, c2), max(c1, c2) + 1):
            canvas.put(r1, c, h_char, style=style)
    else:
        # Z-shaped: vertical from start to midpoint row, horizontal, vertical to end
        if mid_row is None:
            mid_row = (r1 + r2) // 2

        # Vertical: start → mid
        for r in range(min(r1, mid_row), max(r1, mid_row) + 1):
            canvas.put(r, c1, v_char, style=style)
        # Horizontal: c1 → c2 at mid_row
        for c in range(min(c1, c2), max(c1, c2) + 1):
            canvas.put(mid_row, c, h_char, style=style)
        # Vertical: mid → end
        for c in range(min(mid_row, r2), max(mid_row, r2) + 1):
            canvas.put(c, c2, v_char, style=style)

        # Draw corners after lines so they aren't merged with crossing edges
        if not use_ascii:
            if r1 < mid_row:
                corner1 = "┘" if c2 < c1 else "└"
            else:
                corner1 = "┐" if c2 < c1 else "┌"
            canvas.put(mid_row, c1, corner1, merge=False, style=style)

            if r2 > mid_row:
                corner2 = "┌" if c2 < c1 else "┐"
            else:
                corner2 = "└" if c2 < c1 else "┘"
            canvas.put(mid_row, c2, corner2, merge=False, style=style)


def _marker_char(marker: str, direction: str, cs: CharSet) -> str:
    """Return the display character for a relationship marker."""
    if marker == "|>" or marker == "<|":
        # Open triangle (inheritance)
        return {
            "down": cs.inherit_down, "up": cs.inherit_up, "right": cs.inherit_right,
        }.get(direction, cs.inherit_left)
    elif marker == ">" or marker == "<":
        # Filled arrow (dependency)
        return {
            "down": cs.dependency_down, "up": cs.dependency_up, "right": cs.dependency_right,
        }.get(direction, cs.dependency_left)
    elif marker == "*":
        return "◆"
    elif marker == "o":
        return "◇"
    return ""


def _draw_relationship(
    canvas: Canvas,
    rel: Relationship,
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
    layer_of: dict[str, int],
    cs: CharSet,
    use_ascii: bool,
    src_col_offset: int = 0,
    tgt_col_offset: int = 0,
    is_lr: bool = False,
    row_offset: int = 0,
    phase: str = "all",
    run_row: int | None = None,
) -> None:
    """Draw a relationship line between two classes.

    ``phase`` selects what to draw: "lines" draws the connector and its end
    markers so every line is on the canvas before any text, "text" draws the
    label and cardinalities on top, "all" does both. ``row_offset`` shifts a
    horizontal line so several relationships between the same pair of
    classes do not overlap.
    """
    if rel.source not in positions or rel.target not in positions:
        return

    sx, sy = positions[rel.source]
    sw, sh = sizes[rel.source]
    tx, ty = positions[rel.target]
    tw, th = sizes[rel.target]

    s_cx = sx + sw // 2
    s_cy = sy + sh // 2
    t_cx = tx + tw // 2
    t_cy = ty + th // 2

    dx = t_cx - s_cx
    dy = t_cy - s_cy

    # Use layer info to decide connection mode:
    # TB: different layers → vertical, same layer → horizontal
    # LR: different layers → horizontal, same layer → vertical
    s_layer = layer_of.get(rel.source, -1)
    t_layer = layer_of.get(rel.target, -2)
    same_layer = s_layer == t_layer

    if is_lr:
        use_horizontal = not same_layer
    else:
        use_horizontal = same_layer

    # src_dir = direction pointing TOWARD source (for source marker)
    # tgt_dir = direction pointing TOWARD target (for target marker)
    if not use_horizontal:
        start_col = s_cx + src_col_offset
        end_col = t_cx + tgt_col_offset
        if dy > 0:
            start_row = sy + sh  # bottom of source
            end_row = ty - 1     # top of target
            src_dir = "up"       # marker points back toward source (up)
            tgt_dir = "down"     # marker points toward target (down)
        else:
            start_row = sy - 1   # top of source
            end_row = ty + th    # bottom of target
            src_dir = "down"
            tgt_dir = "up"
    else:
        if dx > 0:
            start_col = sx + sw  # right of source
            end_col = tx - 1     # left of target
            src_dir = "left"     # marker points back toward source (left)
            tgt_dir = "right"    # marker points toward target (right)
        else:
            start_col = sx - 1   # left of source
            end_col = tx + tw    # right of target
            src_dir = "right"
            tgt_dir = "left"
        start_row = s_cy
        end_row = t_cy
        if same_layer:
            # Side-by-side boxes: one straight line at a row both boxes share,
            # nudged by row_offset when the pair has several relationships.
            lo = max(sy + 1, ty + 1)
            hi = min(sy + sh - 2, ty + th - 2)
            if lo <= hi:
                row = (s_cy + t_cy) // 2 + row_offset
                start_row = end_row = min(max(row, lo), hi)

    h_char = cs.line_dotted_h if rel.line_style == "dashed" else cs.line_horizontal
    v_char = cs.line_dotted_v if rel.line_style == "dashed" else cs.line_vertical
    style = "edge"

    if phase in ("all", "lines"):
        _draw_routed_line(canvas, start_row, start_col, end_row, end_col,
                          h_char, v_char, use_ascii, style, mid_row=run_row)

        # Draw markers at endpoints
        if not use_ascii:
            src_marker_ch = _marker_char(rel.source_marker, src_dir, cs)
            tgt_marker_ch = _marker_char(rel.target_marker, tgt_dir, cs)
            if src_marker_ch:
                canvas.put(start_row, start_col, src_marker_ch, merge=False, style="arrow")
            if tgt_marker_ch:
                canvas.put(end_row, end_col, tgt_marker_ch, merge=False, style="arrow")
        else:
            # ASCII markers
            if rel.source_marker in ("<|", "<"):
                canvas.put(start_row, start_col, "<", merge=False, style="arrow")
            elif rel.source_marker in ("*", "o"):
                canvas.put(start_row, start_col, rel.source_marker, merge=False, style="arrow")
            if rel.target_marker in ("|>", ">"):
                canvas.put(end_row, end_col, ">", merge=False, style="arrow")
            elif rel.target_marker in ("*", "o"):
                canvas.put(end_row, end_col, rel.target_marker, merge=False, style="arrow")
    if phase == "lines":
        return

    left_col = min(start_col, end_col)
    right_col = max(start_col, end_col)
    mid_r = run_row if run_row is not None else (start_row + end_row) // 2

    # Draw label
    if rel.label:
        label_w = display_width(rel.label)
        if start_row == end_row:
            # Horizontal: label above the line
            mid_c = (start_col + end_col) // 2
            canvas.put_text(mid_r - 1, mid_c - label_w // 2, rel.label, style="edge_label", grow=True)
        elif start_col == end_col:
            # Straight vertical: label to the right of the midpoint
            canvas.put_text(mid_r, start_col + 2, rel.label, style="edge_label", grow=True)
        elif use_horizontal:
            # LR mode Z-route: label beside the vertical run
            canvas.put_text(mid_r, (start_col + end_col) // 2 + 2, rel.label, style="edge_label", grow=True)
        elif right_col - left_col - 2 >= label_w:
            # Z-route: the label rides on the horizontal run between the corners
            canvas.put_text(mid_r, left_col + 2, rel.label, style="edge_label", grow=True)
        else:
            # Too short a run: hang the label off the drop into the target, on
            # the row the track reserved below the run
            canvas.put_text(mid_r + 1, end_col + 2, rel.label, style="edge_label", grow=True)

    # Draw cardinality near endpoints
    if use_horizontal and start_row == end_row:
        # Below the line at each end, so it never collides with the label above
        if rel.source_card:
            col = start_col + 1 if start_col < end_col else start_col - display_width(rel.source_card)
            canvas.put_text(start_row + 1, col, rel.source_card, style="edge_label", grow=True)
        if rel.target_card:
            col = end_col - display_width(rel.target_card) if start_col < end_col else end_col + 1
            canvas.put_text(end_row + 1, col, rel.target_card, style="edge_label", grow=True)
    else:
        if rel.source_card:
            canvas.put_text(start_row, start_col + 1, rel.source_card, style="edge_label", grow=True)
        if rel.target_card:
            canvas.put_text(end_row, end_col + 1, rel.target_card, style="edge_label", grow=True)


def _compute_exit_offsets(
    diagram: ClassDiagram,
    layer_of: dict[str, int],
    end: str = "source",
) -> dict[int, int]:
    """Compute horizontal offset for each relationship's exit point.

    When multiple relationships exit from the bottom of the same source class,
    offset them horizontally to avoid overlap.
    Returns {rel_index: col_offset}.
    """
    # Group relationships by (source, exit_side)
    # exit_side: "bottom" for vertical (different layer), "right"/"left" for horizontal
    groups: dict[tuple[str, str], list[int]] = {}
    for i, rel in enumerate(diagram.relationships):
        s_layer = layer_of.get(rel.source, -1)
        t_layer = layer_of.get(rel.target, -2)
        same_layer = s_layer == t_layer
        if same_layer:
            side = "side"
        else:
            side = "bottom"
        key = (rel.source if end == "source" else rel.target, side)
        groups.setdefault(key, []).append(i)

    offsets: dict[int, int] = {}
    for _key, indices in groups.items():
        if len(indices) <= 1:
            for idx in indices:
                offsets[idx] = 0
            continue
        # Spread offsets symmetrically around center
        n = len(indices)
        # Leave room for a cardinality beside each line
        widest = max(len((diagram.relationships[idx].source_card if end == "source" else diagram.relationships[idx].target_card) or "") for idx in indices)
        spacing = max(4, widest + 2)
        for j, idx in enumerate(indices):
            offsets[idx] = (j - (n - 1) / 2) * spacing
    return offsets


def _compute_row_offsets(
    diagram: ClassDiagram,
    layer_of: dict[str, int],
) -> dict[int, int]:
    """Spread horizontal lines between the same two classes over separate rows.

    Two classes side by side can be linked both ways (``A --> B`` and
    ``B ..> A``); without an offset both lines land on the same row and the
    second erases the first. Returns {rel_index: row_offset}.
    """
    groups: dict[tuple[str, str], list[int]] = {}
    for i, rel in enumerate(diagram.relationships):
        if layer_of.get(rel.source, -1) != layer_of.get(rel.target, -2):
            continue
        key = (min(rel.source, rel.target), max(rel.source, rel.target))
        groups.setdefault(key, []).append(i)

    offsets: dict[int, int] = {}
    for indices in groups.values():
        n = len(indices)
        for j, idx in enumerate(indices):
            offsets[idx] = round((j - (n - 1) / 2) * 2)
    return offsets


def _note_lines(note: Note) -> list[str]:
    """Split note text into display lines (literal \\n becomes line break)."""
    return note.text.split("\\n")


def _note_box_size(note: Note) -> tuple[int, int]:
    """Return (width, height) for a note box."""
    lines = _note_lines(note)
    max_line = max((display_width(l) for l in lines), default=0)
    width = max(max_line + 4, _MIN_BOX_WIDTH)  # 2 padding each side
    height = len(lines) + 2  # top + bottom borders
    return width, height


def _draw_note_box(
    canvas: Canvas, x: int, y: int, note: Note, cs: CharSet,
) -> None:
    """Draw a note box (simple rectangle with text)."""
    width, height = _note_box_size(note)
    lines = _note_lines(note)
    style = "note"

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

    # Text lines
    for li, line in enumerate(lines):
        canvas.put_text(y + 1 + li, x + 2, line, style="label")


def _layout_notes(
    diagram: ClassDiagram,
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
    gap: int = _SIBLING_GAP,
) -> tuple[list[tuple[int, int]], dict[str, tuple[int, int]], int, int]:
    """Position notes and adjust class positions to avoid overlap.

    Returns (note_positions, adjusted_positions, new_width, new_height).
    """
    if not diagram.notes:
        # Compute original canvas bounds
        max_w = max((x + w for (x, _), (w, _) in zip(positions.values(), (sizes[n] for n in positions))), default=0) + _MARGIN
        max_h = max((y + h for (_, y), (_, h) in zip(positions.values(), (sizes[n] for n in positions))), default=0) + _MARGIN
        return [], positions, max_w, max_h

    # Separate targeted and floating notes
    targeted: list[tuple[int, Note]] = []
    floating: list[tuple[int, Note]] = []
    for i, note in enumerate(diagram.notes):
        if note.target and note.target in positions:
            targeted.append((i, note))
        else:
            floating.append((i, note))

    # Compute how much space we need above and to the left for notes
    shift_y = 0  # shift classes down
    shift_x = 0  # shift classes right

    # Floating notes go above all classes
    if floating:
        max_floating_h = max(_note_box_size(n)[1] for _, n in floating) + 2
        shift_y = max_floating_h

    # Targeted notes go to the left of their target class
    if targeted:
        max_note_w = max(_note_box_size(n)[0] for _, n in targeted) + 2
        shift_x = max_note_w

    # Shift all class positions
    adjusted = {}
    for name, (x, y) in positions.items():
        adjusted[name] = (x + shift_x, y + shift_y)

    # Position notes
    note_positions: list[tuple[int, int]] = [(-1, -1)] * len(diagram.notes)

    # Floating notes: top row, advancing horizontally
    float_x = _MARGIN
    for i, note in floating:
        nw, nh = _note_box_size(note)
        note_positions[i] = (float_x, _MARGIN)
        float_x += nw + gap

    # Targeted notes: to the left of their target class, vertically aligned
    for i, note in targeted:
        nw, nh = _note_box_size(note)
        tx, ty = adjusted[note.target]
        nx = max(_MARGIN, tx - nw - 2)
        ny = ty  # same top as target
        note_positions[i] = (nx, ny)

    # Compute canvas bounds
    max_w = 0
    max_h = 0
    for name, (x, y) in adjusted.items():
        w, h = sizes[name]
        max_w = max(max_w, x + w)
        max_h = max(max_h, y + h)
    for i, note in enumerate(diagram.notes):
        nx, ny = note_positions[i]
        nw, nh = _note_box_size(note)
        max_w = max(max_w, nx + nw)
        max_h = max(max_h, ny + nh)

    return note_positions, adjusted, max_w + _MARGIN, max_h + _MARGIN


def render_class_diagram(diagram: ClassDiagram, *, use_ascii: bool = False, padding_x: int = 2, gap: int = 4, cs: CharSet | None = None) -> Canvas:
    """Render a ClassDiagram to a Canvas."""
    cs = cs or default_charset(use_ascii)

    positions, sizes, width, height, layer_of, run_rows = _compute_layout(diagram, padding_x=padding_x, gap=gap)
    if width <= 1 and not diagram.notes:
        return Canvas(1, 1)

    # Position notes, adjusting class positions to make room
    note_positions, positions, width, height = _layout_notes(
        diagram, positions, sizes, gap=gap)

    exit_offsets = _compute_exit_offsets(diagram, layer_of)
    entry_offsets = _compute_exit_offsets(diagram, layer_of, end="target")

    canvas = Canvas(width, height)

    # Draw every relationship line first, then their text, so a later line
    # never overwrites an earlier label or cardinality
    row_offsets = _compute_row_offsets(diagram, layer_of)
    is_lr = diagram.direction == "LR"
    for phase in ("lines", "text"):
        for i, rel in enumerate(diagram.relationships):
            col_offset = int(exit_offsets.get(i, 0))
            entry_offset = int(entry_offsets.get(i, 0))
            _draw_relationship(canvas, rel, positions, sizes, layer_of, cs, use_ascii,
                               src_col_offset=col_offset, tgt_col_offset=entry_offset, is_lr=is_lr,
                               row_offset=row_offsets.get(i, 0), phase=phase,
                               run_row=run_rows.get(i))

    # Draw class boxes on top
    for name, cls in diagram.classes.items():
        if name in positions:
            x, y = positions[name]
            _draw_class_box(canvas, x, y, cls, cs, padding_x=padding_x)

    # Draw notes on top of everything
    for i, note in enumerate(diagram.notes):
        if i < len(note_positions):
            nx, ny = note_positions[i]
            _draw_note_box(canvas, nx, ny, note, cs)

    return canvas
