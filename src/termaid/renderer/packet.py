"""Renderer for packet diagrams.

Renders network packet field layouts as a grid of bit-aligned boxes,
with bit numbers at field boundaries. Fields wrap to new rows every
row_bits (default 32) bits.
"""
from __future__ import annotations

from ..model.packet import Packet
from ..utils import display_width
from .canvas import Canvas


_BITS_PER_COL = 3  # character columns per bit


def render_packet(
    diagram: Packet,
    *,
    use_ascii: bool = False,
    rounded: bool = True,
    padding_y: int = 1,
) -> Canvas:
    """Render a Packet model to a Canvas."""
    if not diagram.fields:
        return Canvas(1, 1)

    row_bits = diagram.row_bits
    cols_per_row = row_bits * _BITS_PER_COL

    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    if use_ascii:
        tl, tr, bl, br = "+", "+", "+", "+"
        tj, bj, lj, rj, cross = "+", "+", "+", "+", "+"
    elif rounded:
        tl, tr, bl, br = "╭", "╮", "╰", "╯"
        tj, bj, lj, rj, cross = "┬", "┴", "├", "┤", "┼"
    else:
        tl, tr, bl, br = "┌", "┐", "└", "┘"
        tj, bj, lj, rj, cross = "┬", "┴", "├", "┤", "┼"

    margin = 1

    # Group fields into rows
    rows: list[list[tuple[int, int, str]]] = []
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
            remaining_label = ""
            bit += bits_in_this_row

    # Each row: 1 (numbers) + 1 (border) + padding_y (content) lines
    # Last row gets an extra bottom border
    row_h = 2 + padding_y  # numbers + border + content lines
    total_h = len(rows) * row_h + 1  # +1 for final bottom border
    total_w = margin + cols_per_row + 1

    canvas = Canvas(total_w + 4, total_h + 1)

    for ri, row_fields in enumerate(rows):
        y_nums = ri * row_h
        y_border = ri * row_h + 1
        y_content = ri * row_h + 1 + (padding_y + 1) // 2  # center content in padding
        row_start_bit = ri * row_bits

        # Bit numbers at field boundaries (start and end of each field)
        placed_nums: set[int] = set()  # x positions already used
        for fi, (cs, ce, _) in enumerate(row_fields):
            # Start bit (left-aligned)
            start_bit = row_start_bit + cs
            start_label = str(start_bit)
            sx = margin + cs * _BITS_PER_COL
            if not any(p in placed_nums for p in range(sx, sx + display_width(start_label) + 1)):
                canvas.put_text(y_nums, sx, start_label, style="edge_label")
                for px in range(sx, sx + display_width(start_label) + 1):  # +1 for gap
                    placed_nums.add(px)

            # End bit (right-aligned at field end)
            end_bit = row_start_bit + ce
            if end_bit != start_bit:  # skip if same as start (single bit)
                end_label = str(end_bit)
                ex = margin + (ce + 1) * _BITS_PER_COL - display_width(end_label)
                # Only show if it doesn't overlap (with 1-char gap)
                if not any(p in placed_nums for p in range(ex - 1, ex + display_width(end_label))):
                    canvas.put_text(y_nums, max(0, ex), end_label, style="edge_label")
                    for px in range(ex, ex + display_width(end_label) + 1):
                        placed_nums.add(px)

        # Right edge │ on number row (aligns with content rows)
        if ri > 0:
            canvas.put(y_nums, margin + cols_per_row, vt, merge=False, style="node")

        # Top border
        for c in range(cols_per_row):
            canvas.put(y_border, margin + c, hz, merge=False, style="node")
        # Right edge
        is_first = ri == 0
        canvas.put(y_border, margin + cols_per_row, tr if is_first else rj, merge=False, style="node")

        # Field separators on border
        for fi, (cs, ce, _) in enumerate(row_fields):
            x = margin + cs * _BITS_PER_COL
            if cs == 0:
                canvas.put(y_border, x, tl if is_first else lj, merge=False, style="node")
            else:
                canvas.put(y_border, x, tj if is_first else cross, merge=False, style="node")

        # Content rows (with padding)
        for py in range(padding_y):
            yr = y_border + 1 + py
            canvas.put(yr, margin, vt, merge=False, style="node")
            canvas.put(yr, margin + cols_per_row, vt, merge=False, style="node")
            for cs, ce, _ in row_fields:
                if cs > 0:
                    canvas.put(yr, margin + cs * _BITS_PER_COL, vt, merge=False, style="node")

        # Labels centered vertically and horizontally
        for cs, ce, label in row_fields:
            x_start = margin + cs * _BITS_PER_COL
            x_end = margin + (ce + 1) * _BITS_PER_COL
            field_w = x_end - x_start

            if label:
                avail = field_w - 2
                disp_label = label
                if display_width(disp_label) > avail:
                    disp_label = label[:max(1, avail - 1)] + "."
                lx = x_start + 1 + (avail - display_width(disp_label)) // 2
                canvas.put_text(y_content, lx, disp_label, style="label")

    # Bottom border
    y_bottom = len(rows) * row_h
    for c in range(cols_per_row):
        canvas.put(y_bottom, margin + c, hz, merge=False, style="node")
    canvas.put(y_bottom, margin, bl, merge=False, style="node")
    canvas.put(y_bottom, margin + cols_per_row, br, merge=False, style="node")

    # Bottom border field separators
    if rows:
        for cs, ce, _ in rows[-1]:
            if cs > 0:
                x = margin + cs * _BITS_PER_COL
                canvas.put(y_bottom, x, bj, merge=False, style="node")

    return canvas
