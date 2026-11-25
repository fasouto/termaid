"""Renderer for packet diagrams.

Renders network packet field layouts as a grid of bit-aligned boxes,
with bit numbers at field boundaries. Fields wrap to new rows every
row_bits (default 32) bits. Each row is a self-contained strip with
its own top/bottom borders.
"""
from __future__ import annotations

from ..model.packet import Packet
from ..utils import display_width, truncate_to_width
from .canvas import Canvas


_BITS_PER_COL = 3  # character columns per bit
# Keys for fields too narrow for any of their label, after the label's first letter.
_KEYS = "123456789abcdefghijklmnopqrstuvwxyz"


def render_packet(
    diagram: Packet,
    *,
    use_ascii: bool = False,
    rounded: bool = True,
    padding_y: int = 1,
    max_label_width: int | None = None,
) -> Canvas:
    """Render a Packet model to a Canvas.

    With *max_label_width*, rows hold half as many bits, then half again,
    until a row is no wider than it.
    """
    if not diagram.fields:
        return Canvas(1, 1)

    row_bits = diagram.row_bits
    if max_label_width is not None:
        while row_bits > 1 and row_bits * _BITS_PER_COL + 2 > max_label_width:
            row_bits //= 2
    cols_per_row = row_bits * _BITS_PER_COL
    # The labels need a row inside the borders.
    padding_y = max(padding_y, 1)

    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    if use_ascii:
        tl, tr, bl, br = "+", "+", "+", "+"
        tj, bj = "+", "+"
    elif rounded:
        tl, tr, bl, br = "╭", "╮", "╰", "╯"
        tj, bj = "┬", "┴"
    else:
        tl, tr, bl, br = "┌", "┐", "└", "┘"
        tj, bj = "┬", "┴"

    margin = 1
    shown = _shown_labels(diagram, row_bits)

    # Group fields into rows
    rows: list[list[tuple[int, int, str]]] = []
    continued_rows: set[int] = set()
    for field in diagram.fields:
        bit = field.start
        remaining_label = field.label
        while bit <= field.end:
            row_idx = bit // row_bits
            col_in_row = bit % row_bits
            bits_in_this_row = min(field.end - bit + 1, row_bits - col_in_row)
            col_start = col_in_row
            col_end = col_in_row + bits_in_this_row - 1

            while len(rows) <= row_idx:
                rows.append([])

            rows[row_idx].append((col_start, col_end, remaining_label))
            if bit > field.start:
                continued_rows.add(row_idx)
            remaining_label = ""
            bit += bits_in_this_row

    # Remove trailing rows that have no labels
    while (
        rows
        and len(rows) - 1 not in continued_rows
        and all(not label for _, _, label in rows[-1])
    ):
        rows.pop()

    title_h = 1 if diagram.title else 0
    # Each row: 1 (numbers) + 1 (top border) + padding_y (content) + 1 (bottom border)
    row_h = 3 + padding_y
    total_h = title_h + len(rows) * row_h
    total_w = margin + cols_per_row + 1

    canvas = Canvas(max(total_w + 4, margin + display_width(diagram.title) + 1), total_h + 10)  # extra for legend

    if diagram.title:
        title_x = margin + max(0, (cols_per_row - display_width(diagram.title)) // 2)
        canvas.put_text(0, title_x, diagram.title, style="label")

    for ri, row_fields in enumerate(rows):
        y_nums = title_h + ri * row_h
        y_top = y_nums + 1
        y_bottom = y_nums + 2 + padding_y
        y_content = y_top + (padding_y + 1) // 2
        row_start_bit = ri * row_bits
        # A row ends where its last field ends, as in Mermaid.
        row_cols = (row_fields[-1][1] + 1) * _BITS_PER_COL if row_fields else cols_per_row

        # --- Bit numbers ---
        # Cells taken by a number and the gap after it.
        placed_nums: set[int] = set()

        def place(x: int, label: str) -> None:
            if not any(p in placed_nums for p in range(x - 1, x + display_width(label) + 1)):
                canvas.put_text(y_nums, x, label, style="edge_label")
                placed_nums.update(range(x, x + display_width(label)))

        # The row's first and last bits always show.
        if row_fields:
            first_cs = row_fields[0][0]
            start_label = str(row_start_bit + first_cs)
            canvas.put_text(y_nums, margin + first_cs * _BITS_PER_COL, start_label, style="edge_label")
            placed_nums.update(range(margin + first_cs * _BITS_PER_COL,
                                     margin + first_cs * _BITS_PER_COL + display_width(start_label)))
            last_ce = row_fields[-1][1]
            end_label = str(row_start_bit + last_ce)
            if last_ce != first_cs:
                place(margin + (last_ce + 1) * _BITS_PER_COL - display_width(end_label), end_label)

        # Each field's first and last bit, where there is room
        for fi in range(1, len(row_fields)):
            cs, ce, _ = row_fields[fi]
            prev_cs, prev_ce, _ = row_fields[fi - 1]
            if prev_ce > prev_cs:
                end_label = str(row_start_bit + prev_ce)
                place(margin + (prev_ce + 1) * _BITS_PER_COL - display_width(end_label), end_label)
            place(margin + cs * _BITS_PER_COL + 1, str(row_start_bit + cs))

        # --- Top border ---
        canvas.put(y_top, margin, tl, merge=False, style="node")
        for c in range(1, row_cols):
            canvas.put(y_top, margin + c, hz, merge=False, style="node")
        canvas.put(y_top, margin + row_cols, tr, merge=False, style="node")

        # Field separators on top border
        for cs, ce, _ in row_fields:
            if cs > 0:
                canvas.put(y_top, margin + cs * _BITS_PER_COL, tj, merge=False, style="node")

        # --- Content rows ---
        for py in range(padding_y):
            yr = y_top + 1 + py
            canvas.put(yr, margin, vt, merge=False, style="node")
            canvas.put(yr, margin + row_cols, vt, merge=False, style="node")
            for cs, ce, _ in row_fields:
                if cs > 0:
                    canvas.put(yr, margin + cs * _BITS_PER_COL, vt, merge=False, style="node")

        # Labels centered
        for cs, ce, label in row_fields:
            x_start = margin + cs * _BITS_PER_COL
            x_end = margin + (ce + 1) * _BITS_PER_COL
            field_w = x_end - x_start

            if label:
                avail = field_w - 2
                disp_label = shown.get((row_start_bit + cs, label)) or truncate_to_width(label, avail)
                lx = x_start + 1 + (avail - display_width(disp_label)) // 2
                canvas.put_text(y_content, lx, disp_label, style="label")

        # --- Bottom border ---
        canvas.put(y_bottom, margin, bl, merge=False, style="node")
        for c in range(1, row_cols):
            canvas.put(y_bottom, margin + c, hz, merge=False, style="node")
        canvas.put(y_bottom, margin + row_cols, br, merge=False, style="node")

        # Field separators on bottom border
        for cs, ce, _ in row_fields:
            if cs > 0:
                canvas.put(y_bottom, margin + cs * _BITS_PER_COL, bj, merge=False, style="node")

    # Legend for truncated labels
    truncated = [
        (shown[(field.start, field.label)], field.label, field.start, field.end)
        for field in diagram.fields
        if (field.start, field.label) in shown
    ]

    if truncated:
        y_legend = total_h + 1
        needed_h = y_legend + len(truncated) + 1
        if needed_h > canvas.height:
            canvas.resize(canvas.width, needed_h)
        for i, (short, full, start, end) in enumerate(truncated):
            if start == end:
                bits = f"[{start}]"
            else:
                bits = f"[{start}-{end}]"
            canvas.put_text(y_legend + i, margin, f"{short} = {full} {bits}", style="edge_label")

    return canvas


def _shown_labels(diagram: Packet, row_bits: int) -> dict[tuple[int, str], str]:
    """What each field too narrow for its label shows instead, by (start bit, label).

    A label cut short keeps as much as fits. A field with room for one
    character shows a key that no other cut label uses, which the legend
    explains: the label's first letter when it is free, else a digit or a
    letter, so fields such as one-bit flags can be told apart.
    """
    shown: dict[tuple[int, str], str] = {}
    keyed: list[tuple[int, str]] = []
    for field in diagram.fields:
        # The label sits in the field's first row.
        bits = min(field.bits, row_bits - field.start % row_bits)
        avail = bits * _BITS_PER_COL - 2
        if not field.label or display_width(field.label) <= avail:
            continue
        if avail <= 1:
            keyed.append((field.start, field.label))
        else:
            shown[(field.start, field.label)] = truncate_to_width(field.label, avail)
    used = set(shown.values())
    for start, label in keyed:
        key = next((k for k in (label[0], *_KEYS) if k not in used and display_width(k) == 1), ".")
        used.add(key)
        shown[(start, label)] = key
    return shown
