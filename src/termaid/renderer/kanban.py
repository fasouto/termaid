"""Renderer for kanban board diagrams.

Renders columns side by side with cards stacked vertically inside
each column, using box-drawing characters for borders.
"""
from __future__ import annotations

from ..model.kanban import Kanban
from ..utils import display_width, truncate_to_width
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet


_COL_PAD = 2      # horizontal padding inside columns
_CARD_PAD = 1     # padding inside card borders
_COL_GAP = 2      # gap between columns
_CARD_GAP = 1     # gap between cards in a column


def render_kanban(
    diagram: Kanban,
    *,
    use_ascii: bool = False,
    padding_x: int = _CARD_PAD,
    gap: int = _COL_GAP,
) -> Canvas:
    """Render a Kanban model to a Canvas."""
    cs = ASCII if use_ascii else UNICODE

    if not diagram.columns:
        return Canvas(1, 1)

    # Compute column widths (based on widest card or column title).
    # Card text sits inside card borders, inset _COL_PAD from each column
    # edge; the centered title needs the column borders plus a space each
    # side. padding_x beyond the default adds extra slack.
    col_widths: list[int] = []
    for col in diagram.columns:
        title_w = display_width(col.title)
        card_w = max((display_width(card.title) + (display_width(card.metadata) + 1 if card.metadata else 0)
                      for card in col.cards), default=0)
        need = max(title_w + 4, card_w + 2 + 2 * _COL_PAD)
        col_widths.append(max(need + (padding_x - _CARD_PAD) * 2, 10))

    # Compute column heights (title + cards)
    col_heights: list[int] = []
    for col in diagram.columns:
        h = 3  # top border + title + separator
        for ci, card in enumerate(col.cards):
            h += 3  # card: top + content + bottom
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

        # Card box (lighter shade of column color)
        canvas.put_text(card_y, cx, card_tl + card_hz * (cw - 2) + card_tr, style=card_style)
        canvas.put(card_y + 1, cx, card_vt, merge=False, style=card_style)
        canvas.put(card_y + 1, cx + cw - 1, card_vt, merge=False, style=card_style)
        canvas.put_text(card_y + 2, cx, card_bl + card_hz * (cw - 2) + card_br, style=card_style)

        # Card interior bg
        for c in range(cx + 1, cx + cw - 1):
            canvas._style_grid[card_y + 1][c] = card_style

        # Card content
        text = card.title
        if card.metadata:
            text += " " + card.metadata
        text = truncate_to_width(text, cw - 2)
        canvas.put_text(card_y + 1, cx + 1, text, style=card_style)

        card_y += 3 + _CARD_GAP
