"""Renderer for kanban board diagrams.

Renders columns side by side with cards stacked vertically inside
each column, using box-drawing characters for borders.
"""
from __future__ import annotations

from ..model.kanban import Kanban
from ..utils import display_width, truncate_to_width
from .canvas import Canvas
from .charset import CharSet, default_charset


_COL_PAD = 2      # horizontal padding inside columns
_CARD_PAD = 1     # padding inside card borders
_COL_GAP = 2      # gap between columns
_CARD_GAP = 1     # gap between cards in a column


_PRIORITY_BORDER = {
    "very high": ("I", "┃"), "high": ("I", "┃"),
    "low": (":", "┆"), "very low": (":", "┆"),
}


def _footer(card) -> str:
    """The ticket and assignee line under a card's title, "" when it has neither."""
    return " ".join(part for part in (card.ticket, card.assigned) if part)


def render_kanban(
    diagram: Kanban,
    *,
    use_ascii: bool = False,
    cs: CharSet | None = None,
    padding_x: int = _CARD_PAD,
    gap: int = _COL_GAP,
) -> Canvas:
    """Render a Kanban model to a Canvas."""
    cs = cs or default_charset(use_ascii)

    if not diagram.columns:
        return Canvas(1, 1)

    # Compute column widths (based on widest card or column title).
    # Card text sits inside card borders, inset _COL_PAD from each column
    # edge; the centered title needs the column borders plus a space each
    # side. padding_x beyond the default adds extra slack; below it, card
    # text would be cut short.
    padding_x = max(padding_x, _CARD_PAD)
    col_widths: list[int] = []
    for col in diagram.columns:
        title_w = display_width(col.title)
        card_w = max((max(display_width(card.title), display_width(_footer(card)))
                      for card in col.cards), default=0)
        need = max(title_w + 4, card_w + 2 + 2 * _COL_PAD)
        col_widths.append(max(need + (padding_x - _CARD_PAD) * 2, 10))

    # Compute column heights (title + cards)
    col_heights: list[int] = []
    for col in diagram.columns:
        h = 3  # top border + title + separator
        for ci, card in enumerate(col.cards):
            h += 3 + bool(_footer(card))  # card: top + content (+ footer) + bottom
            if ci < len(col.cards) - 1:
                h += _CARD_GAP
        h += 1  # bottom border
        col_heights.append(h)

    total_height = max(col_heights) if col_heights else 4
    total_width = sum(col_widths) + gap * (len(col_widths) - 1)

    canvas = Canvas(total_width + 1, total_height + 1)

    # Draw each column with a rotating section style
    x = 0
    for ci, col in enumerate(diagram.columns):
        w = col_widths[ci]
        section_style = f"section:{ci}"
        _draw_column(canvas, cs, col, x, 0, w, total_height, use_ascii, section_style)
        x += w + gap

    return canvas


def _draw_column(
    canvas: Canvas, cs: CharSet,
    col, x: int, y: int, w: int, h: int,
    use_ascii: bool,
    section_style: str = "subgraph",
) -> None:
    """Draw a single kanban column with its cards."""
    tl = "+" if use_ascii else "╭"
    tr = "+" if use_ascii else "╮"
    bl = "+" if use_ascii else "╰"
    br = "+" if use_ascii else "╯"
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"

    # Fill entire column interior with section bg (for solid themes)
    card_style = section_style + ":deep"
    for r in range(y + 1, y + h - 1):
        for c in range(x + 1, x + w - 1):
            canvas._style_grid[r][c] = section_style

    # Column border
    canvas.put_text(y, x, tl + hz * (w - 2) + tr, style=section_style)
    canvas.put_text(y + h - 1, x, bl + hz * (w - 2) + br, style=section_style)
    for r in range(y + 1, y + h - 1):
        canvas.put(r, x, vt, merge=False, style=section_style)
        canvas.put(r, x + w - 1, vt, merge=False, style=section_style)

    # Column title (centered, bold)
    title = truncate_to_width(col.title, w - 4)
    title_x = x + (w - display_width(title)) // 2
    canvas.put_text(y + 1, title_x, title, style=section_style)

    # Separator under title
    sep = hz * (w - 2)
    canvas.put_text(y + 2, x + 1, sep, style=section_style)

    # Cards
    card_y = y + 3
    card_tl = "+" if use_ascii else "┌"
    card_tr = "+" if use_ascii else "┐"
    card_bl = "+" if use_ascii else "└"
    card_br = "+" if use_ascii else "┘"
    card_hz = "-" if use_ascii else "─"
    card_vt = "|" if use_ascii else "│"

    for ci, card in enumerate(col.cards):
        cw = w - 2 * _COL_PAD
        cx = x + _COL_PAD

        footer = _footer(card)
        rows = 2 if footer else 1
        # Mermaid marks a card's priority on its left border.
        left = _PRIORITY_BORDER.get(card.priority.lower(), ("|", card_vt))[0 if use_ascii else 1]

        # Card box (lighter shade of column color)
        canvas.put_text(card_y, cx, card_tl + card_hz * (cw - 2) + card_tr, style=card_style)
        for r in range(card_y + 1, card_y + 1 + rows):
            canvas.put(r, cx, left, merge=False, style=card_style)
            canvas.put(r, cx + cw - 1, card_vt, merge=False, style=card_style)
            for c in range(cx + 1, cx + cw - 1):
                canvas._style_grid[r][c] = card_style
        canvas.put_text(card_y + 1 + rows, cx, card_bl + card_hz * (cw - 2) + card_br, style=card_style)

        canvas.put_text(card_y + 1, cx + 1, truncate_to_width(card.title, cw - 2), style=card_style)
        if footer:
            # Ticket on the left, assignee on the right, as Mermaid places them.
            gap = cw - 2 - display_width(footer)
            if card.assigned and gap > 0:
                footer = card.ticket + " " * (gap + bool(card.ticket)) + card.assigned
            canvas.put_text(card_y + 2, cx + 1, truncate_to_width(footer, cw - 2), style=card_style)

        card_y += 2 + rows + _CARD_GAP
