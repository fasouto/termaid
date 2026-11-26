"""Renderer for class diagrams.

Renders a ClassDiagram directly to a Canvas; boxes are placed and lines
routed by the layered layout shared with ER diagrams.
"""
from __future__ import annotations

from ..model.classdiagram import ClassDef, ClassDiagram, Note, Relationship
from .canvas import Canvas
from .charset import CharSet, default_charset
from .relation_layout import End, Link, attach_end, draw_route, layout, put_label
from ..utils import display_width

# ── layout constants ──────────────────────────────────────────────
_CLASS_PAD = 2       # horizontal padding inside class box
_MIN_BOX_WIDTH = 16  # minimum class box width


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
    lines.append(cls.display_name)

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
    padding_x: int = _CLASS_PAD, size: tuple[int, int] = (0, 0),
) -> tuple[int, int]:
    """Draw a class box, at least ``size`` big, and return (width, height)."""
    natural = _compute_box_size(cls, padding_x=padding_x)
    width, height = max(size[0], natural[0]), max(size[1], natural[1])
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

    name_col = x + (width - display_width(cls.display_name)) // 2
    canvas.put_text(row, name_col, cls.display_name, style="label")
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


def _marker_char(marker: str, toward: str, cs: CharSet, use_ascii: bool) -> str:
    """The character for a relationship end marker pointing ``toward`` its box."""
    if marker in ("|>", "<|"):
        if use_ascii:
            # ASCII has no open triangle; keep inheritance apart from arrows.
            return {"down": "V", "up": "A", "right": "|>", "left": "<|"}[toward]
        return {"down": cs.inherit_down, "up": cs.inherit_up, "right": cs.inherit_right,
                "left": cs.inherit_left}[toward]
    if marker in (">", "<"):
        return {"down": cs.dependency_down, "up": cs.dependency_up, "right": cs.dependency_right,
                "left": cs.dependency_left}[toward]
    if marker == "*":
        return "*" if use_ascii else "◆"
    if marker == "o":
        return "o" if use_ascii else "◇"
    return ""


def _put_marker(canvas: Canvas, end: End, ch: str) -> None:
    """Draw a marker at a line's end; a two-cell ASCII marker reads outwards
    from the box (``<|`` on the left of a line, ``|>`` on its right)."""
    if len(ch) == 2:
        step = 1 if end.toward == "left" else -1
        cells = ch if end.toward == "left" else ch[::-1]
        for j, cell in enumerate(cells):
            canvas.put(end.row, end.col + j * step, cell, merge=False, style="arrow")
        return
    canvas.put(end.row, end.col, ch, merge=False, style="arrow")


def _link(rel: Relationship) -> Link:
    # The marker points at the parent: "Animal <|-- Duck" and "Duck --|> Animal"
    # both put Animal above Duck. Other relationships run source to target.
    a_above = not (rel.target_marker == "|>" and rel.source_marker != "<|")
    return Link(rel.source, rel.target, a_above, rel.label, rel.source_card, rel.target_card)


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


def _namespace_frames(
    diagram: ClassDiagram, positions: dict[str, tuple[int, int]], sizes: dict[str, tuple[int, int]],
) -> list[tuple[str, int, int, int, int]]:
    """(title, top, left, bottom, right) of a frame around each namespace.

    A namespace whose classes did not end up next to each other gets no
    frame, since it would have to take in other classes.
    """
    frames = []
    for title, members in diagram.namespaces.items():
        inside = [m for m in members if m in positions]
        if not inside:
            continue
        top = min(positions[m][1] for m in inside) - 1
        left = min(positions[m][0] for m in inside) - 2
        bottom = max(positions[m][1] + sizes[m][1] for m in inside)
        right = max(positions[m][0] + sizes[m][0] for m in inside) + 1
        right = max(right, left + display_width(title) + 5)
        if top < 0 or left < 0:
            continue
        clash = any(
            x <= right + 1 and x + sizes[n][0] - 1 >= left - 1 and y <= bottom + 1 and y + sizes[n][1] - 1 >= top - 1
            for n, (x, y) in positions.items() if n not in inside
        )
        if not clash:
            frames.append((title, top, left, bottom, right))
    return frames


def _draw_frame(canvas: Canvas, frame: tuple[str, int, int, int, int], cs: CharSet) -> None:
    _title, top, left, bottom, right = frame
    canvas.resize(max(canvas.width, right + 1), max(canvas.height, bottom + 1))
    for c in range(left + 1, right):
        canvas.put(top, c, cs.sg_horizontal, style="subgraph")
        canvas.put(bottom, c, cs.sg_horizontal, style="subgraph")
    for r in range(top + 1, bottom):
        canvas.put(r, left, cs.sg_vertical, style="subgraph")
        canvas.put(r, right, cs.sg_vertical, style="subgraph")
    canvas.put(top, left, cs.sg_top_left, style="subgraph")
    canvas.put(top, right, cs.sg_top_right, style="subgraph")
    canvas.put(bottom, left, cs.sg_bottom_left, style="subgraph")
    canvas.put(bottom, right, cs.sg_bottom_right, style="subgraph")


def render_class_diagram(diagram: ClassDiagram, *, use_ascii: bool = False, padding_x: int = 2, gap: int = 4, cs: CharSet | None = None) -> Canvas:
    """Render a ClassDiagram to a Canvas."""
    cs = cs or default_charset(use_ascii)
    # Text starts padding_x columns in from the border: at 0 it would cover it.
    padding_x = max(padding_x, 1)

    sizes = {name: _compute_box_size(cls, padding_x=padding_x) for name, cls in diagram.classes.items()}
    links = [_link(rel) for rel in diagram.relationships]
    # A note is a box of its own, tied to its class by a dashed line.
    notes: dict[str, Note] = {}
    for i, note in enumerate(diagram.notes):
        key = f"\x00note{i}"
        notes[key] = note
        sizes[key] = _note_box_size(note)
        if note.target in diagram.classes:
            links.append(Link(key, note.target))
    if not sizes:
        return Canvas(1, 1)

    lay = layout(sizes, links, gap, diagram.direction)
    canvas = Canvas(lay.width, lay.height)
    corner = cs.corner_top_left if use_ascii else None
    frames = _namespace_frames(diagram, lay.positions, lay.sizes)
    for frame in frames:
        _draw_frame(canvas, frame, cs)

    # Every line first, then the text, so a later line never cuts a label.
    n_rels = len(diagram.relationships)
    for i, route in enumerate(lay.routes):
        if route is None:
            continue
        dashed = i >= n_rels or diagram.relationships[i].line_style == "dashed"
        h = cs.line_dotted_h if dashed else cs.line_horizontal
        v = cs.line_dotted_v if dashed else cs.line_vertical
        draw_route(canvas, route, h, v, corner)
    for rel, route in zip(diagram.relationships, lay.routes):
        if route is None:
            continue
        for marker, end in ((rel.source_marker, route.a), (rel.target_marker, route.b)):
            ch = _marker_char(marker, end.toward, cs, use_ascii)
            if ch:
                _put_marker(canvas, end, ch)
    for rel, route in zip(diagram.relationships, lay.routes):
        if route is None:
            continue
        for text, at in ((rel.source_card, route.card_a_at), (rel.target_card, route.card_b_at),
                         (rel.label, route.label_at)):
            if text and at is not None:
                put_label(canvas, at, text)

    for title, top, left, _, _ in frames:
        canvas.put_text(top, left + 2, f" {title} ", style="subgraph_label")

    for name, (x, y) in lay.positions.items():
        if name in notes:
            _draw_note_box(canvas, x, y, notes[name], cs)
        else:
            _draw_class_box(canvas, x, y, diagram.classes[name], cs, padding_x=padding_x,
                            size=lay.sizes[name])
    for rel, route in zip(diagram.relationships, lay.routes):
        if route is not None and rel.source == rel.target:
            if not rel.source_marker:
                attach_end(canvas, route, route.a, cs)
            if not rel.target_marker:
                attach_end(canvas, route, route.b, cs)

    return canvas
