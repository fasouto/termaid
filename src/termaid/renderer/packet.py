"""Renderer for packet diagrams.

Renders network packet field layouts as a grid of bit-aligned boxes,
with bit numbers at field boundaries. Fields wrap to new rows every
row_bits (default 32) bits. Each row is a self-contained strip with
its own top/bottom borders.
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
        tj, bj = "+", "+"
    elif rounded:
        tl, tr, bl, br = "╭", "╮", "╰", "╯"
        tj, bj = "┬", "┴"
    else:
        tl, tr, bl, br = "┌", "┐", "└", "┘"
        tj, bj = "┬", "┴"

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

    # Remove trailing rows that have no labels
    while rows and all(not label for _, _, label in rows[-1]):
        rows.pop()

    # Each row: 1 (numbers) + 1 (top border) + padding_y (content) + 1 (bottom border)
    row_h = 3 + padding_y
    total_h = len(rows) * row_h
    total_w = margin + cols_per_row + 1

    canvas = Canvas(total_w + 4, total_h + 10)  # extra for legend

    for ri, row_fields in enumerate(rows):
        y_nums = ri * row_h
        y_top = ri * row_h + 1
        y_bottom = ri * row_h + 2 + padding_y
        y_content = y_top + (padding_y + 1) // 2
        row_start_bit = ri * row_bits

        # --- Bit numbers ---
        placed_nums: set[int] = set()

        # Only show bit numbers for fields wide enough to display them
        # without crowding. Skip intermediate numbers for narrow fields.
        min_field_cols = 4  # minimum columns to show a number

        # End label of the entire row (right-aligned, always shown)
        if row_fields:
            last_ce = row_fields[-1][1]
            end_bit = row_start_bit + last_ce
            end_label = str(end_bit)
            ex = margin + (last_ce + 1) * _BITS_PER_COL - display_width(end_label)
            canvas.put_text(y_nums, ex, end_label, style="edge_label")
            for px in range(ex, ex + display_width(end_label) + 1):
                placed_nums.add(px)

        # Start label of the entire row (left-aligned, always shown)
        if row_fields:
            first_cs = row_fields[0][0]
            start_bit = row_start_bit + first_cs
            start_label = str(start_bit)
            sx = margin + first_cs * _BITS_PER_COL
            canvas.put_text(y_nums, sx, start_label, style="edge_label")
            for px in range(sx, sx + display_width(start_label)):
                placed_nums.add(px)

        # Intermediate boundary numbers (only when fields are wide enough)
        for fi in range(1, len(row_fields)):
            cs, ce, _ = row_fields[fi]
            prev_cs, prev_ce, _ = row_fields[fi - 1]
            prev_width = (prev_ce - prev_cs + 1) * _BITS_PER_COL
            cur_width = (ce - cs + 1) * _BITS_PER_COL

            # Show end of previous field
            if prev_width >= min_field_cols:
                end_bit = row_start_bit + prev_ce
                end_label = str(end_bit)
                ex = margin + (prev_ce + 1) * _BITS_PER_COL - display_width(end_label)
                if not any(p in placed_nums for p in range(ex, ex + display_width(end_label) + 1)):
                    canvas.put_text(y_nums, ex, end_label, style="edge_label")
                    for px in range(ex, ex + display_width(end_label) + 1):
                        placed_nums.add(px)

            # Show start of current field
            if cur_width >= min_field_cols:
                start_bit = row_start_bit + cs
                start_label = str(start_bit)
                sx = margin + cs * _BITS_PER_COL + 1
                if not any(p in placed_nums for p in range(sx, sx + display_width(start_label))):
                    canvas.put_text(y_nums, sx, start_label, style="edge_label")
                    for px in range(sx, sx + display_width(start_label)):
                        placed_nums.add(px)

        # --- Top border ---
        canvas.put(y_top, margin, tl, merge=False, style="node")
        for c in range(1, cols_per_row):
            canvas.put(y_top, margin + c, hz, merge=False, style="node")
        canvas.put(y_top, margin + cols_per_row, tr, merge=False, style="node")

        # Field separators on top border
        for cs, ce, _ in row_fields:
            if cs > 0:
                canvas.put(y_top, margin + cs * _BITS_PER_COL, tj, merge=False, style="node")

        # --- Content rows ---
        for py in range(padding_y):
            yr = y_top + 1 + py
            canvas.put(yr, margin, vt, merge=False, style="node")
            canvas.put(yr, margin + cols_per_row, vt, merge=False, style="node")
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
                disp_label = label
                if display_width(disp_label) > avail:
                    disp_label = label[:max(1, avail - 1)] + "."
                lx = x_start + 1 + (avail - display_width(disp_label)) // 2
                canvas.put_text(y_content, lx, disp_label, style="label")

        # --- Bottom border ---
        canvas.put(y_bottom, margin, bl, merge=False, style="node")
        for c in range(1, cols_per_row):
            canvas.put(y_bottom, margin + c, hz, merge=False, style="node")
        canvas.put(y_bottom, margin + cols_per_row, br, merge=False, style="node")

        # Field separators on bottom border
        for cs, ce, _ in row_fields:
            if cs > 0:
                canvas.put(y_bottom, margin + cs * _BITS_PER_COL, bj, merge=False, style="node")

    # Legend for truncated labels
    truncated: list[tuple[str, str, int, int]] = []
    for field in diagram.fields:
        avail = field.bits * _BITS_PER_COL - 2
        if avail < display_width(field.label) and field.label:
            short = field.label[:max(1, avail - 1)] + "."
            truncated.append((short, field.label, field.start, field.end))

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
