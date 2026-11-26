"""Renderer for ER diagrams.

Renders an ERDiagram directly to a Canvas; boxes are placed and lines
routed by the layered layout shared with class diagrams.
"""
from __future__ import annotations

from ..model.erdiagram import Entity, ERDiagram
from .canvas import Canvas
from .charset import CharSet, default_charset
from .relation_layout import Link, attach_end, draw_route, layout, put_label
from ..utils import display_width

# ── layout constants ──────────────────────────────────────────────
_PAD = 2             # horizontal padding inside entity box
_MIN_BOX_WIDTH = 16  # minimum entity box width


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
    max_text = max((display_width(l) for l in all_lines), default=0)
    width = max(max_text + padding_x * 2, _MIN_BOX_WIDTH)

    # Height: top border + name row + [divider + attr rows] + bottom border
    height = 2 + len(lines)  # borders + name
    if attr_lines:
        height += 1 + len(attr_lines)  # divider + attributes

    return width, height


def _draw_entity_box(
    canvas: Canvas, x: int, y: int, entity: Entity, cs: CharSet,
    padding_x: int = _PAD, size: tuple[int, int] = (0, 0),
) -> tuple[int, int]:
    """Draw an entity box, at least ``size`` big, and return (width, height)."""
    natural = _compute_box_size(entity, padding_x=padding_x)
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

    # Name (centered)
    row = y + 1
    name = entity.display_name
    name_col = x + (width - display_width(name)) // 2
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


def render_er_diagram(diagram: ERDiagram, *, use_ascii: bool = False, padding_x: int = 2, gap: int = 4, cs: CharSet | None = None) -> Canvas:
    """Render an ERDiagram to a Canvas."""
    cs = cs or default_charset(use_ascii)
    # Text starts padding_x columns in from the border: at 0 it would cover it.
    padding_x = max(padding_x, 1)

    sizes = {name: _compute_box_size(e, padding_x=padding_x) for name, e in diagram.entities.items()}
    if not sizes:
        return Canvas(1, 1)
    links = [Link(rel.entity1, rel.entity2, True, rel.label, _card_text(rel.card1), _card_text(rel.card2))
             for rel in diagram.relationships]
    lay = layout(sizes, links, gap, diagram.direction)
    canvas = Canvas(lay.width, lay.height)
    corner = cs.corner_top_left if use_ascii else None

    # Every line first, then the text, so a later line never cuts a label.
    for rel, route in zip(diagram.relationships, lay.routes):
        if route is None:
            continue
        dashed = rel.line_style == "dashed"
        h = cs.line_dotted_h if dashed else cs.line_horizontal
        v = cs.line_dotted_v if dashed else cs.line_vertical
        draw_route(canvas, route, h, v, corner)
    for link, route in zip(links, lay.routes):
        if route is None:
            continue
        for text, at in ((link.card_a, route.card_a_at), (link.card_b, route.card_b_at),
                         (link.label, route.label_at)):
            if text and at is not None:
                put_label(canvas, at, text)

    for name, (x, y) in lay.positions.items():
        _draw_entity_box(canvas, x, y, diagram.entities[name], cs, padding_x=padding_x,
                         size=lay.sizes[name])
    # A self-relationship's line comes back into the side of its box.
    for rel, route in zip(diagram.relationships, lay.routes):
        if route is not None and rel.entity1 == rel.entity2:
            attach_end(canvas, route, route.a, cs)
            attach_end(canvas, route, route.b, cs)

    return canvas
