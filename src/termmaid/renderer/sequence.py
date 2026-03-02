"""Renderer for sequence diagrams.

Renders a SequenceDiagram directly to a Canvas, bypassing the grid layout
and A* edge routing used by flowcharts.
"""
from __future__ import annotations

from ..model.sequence import Message, Note, SequenceDiagram
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from .shapes import draw_rectangle, draw_cylinder


# ── layout constants ──────────────────────────────────────────────
_BOX_PAD = 4          # horizontal padding inside participant boxes
_BOX_HEIGHT = 3       # participant box height
_ACTOR_HEIGHT = 5     # actor stick-figure height (head, body, legs, gap, label)
_MIN_GAP = 16         # minimum gap between participant centers
_EVENT_ROW_H = 2      # rows per message event
_NOTE_ROW_H = 4       # rows per note event (3-row box + 1 gap)
_TOP_MARGIN = 0
_BOTTOM_MARGIN = 1

# Height per participant kind (for header sizing)
_KIND_HEIGHT = {
    "participant": 3,
    "actor": 5,
    "database": 5,
    "queue": 5,
    "boundary": 5,
    "control": 5,
    "entity": 5,
    "collections": 5,
}


def _participant_index(diagram: SequenceDiagram, pid: str) -> int:
    for i, p in enumerate(diagram.participants):
        if p.id == pid:
            return i
    return -1


def _effective_label(msg: Message, msg_number: int | None) -> str:
    """Return the displayed label, with optional autonumber prefix."""
    if msg_number is not None:
        prefix = f"{msg_number}: "
        return prefix + msg.label if msg.label else prefix.rstrip()
    return msg.label


def _compute_layout(
    diagram: SequenceDiagram,
    autonumber: bool,
) -> tuple[list[int], list[int], int, int, int, list[int]]:
    """Compute column center positions and box widths.

    Returns (col_centers, box_widths, canvas_width, canvas_height, header_height, row_offsets).
    """
    n = len(diagram.participants)
    if n == 0:
        return [], [], 0, 0, 0, []

    # Box widths based on label length
    box_widths = [max(len(p.label) + _BOX_PAD, 12) for p in diagram.participants]

    # Header height: tallest participant kind
    header_height = max(_KIND_HEIGHT.get(p.kind, 3) for p in diagram.participants)

    # Compute per-event heights and effective labels for gap computation
    event_heights: list[int] = []
    effective_labels: list[str] = []  # only for Messages
    msg_counter = 0
    for ev in diagram.events:
        if isinstance(ev, Note):
            event_heights.append(_NOTE_ROW_H)
            effective_labels.append("")
        else:
            msg_counter += 1
            eff = _effective_label(ev, msg_counter if autonumber else None)
            effective_labels.append(eff)
            event_heights.append(_EVENT_ROW_H)

    # Compute per-gap minimum widths based on message labels between adjacent pairs
    gap_mins = [_MIN_GAP] * (n - 1)
    msg_idx = 0
    for ev_idx, ev in enumerate(diagram.events):
        if isinstance(ev, Note):
            # Notes may need gap expansion
            note_width = len(ev.text) + 4
            for pid in ev.participants:
                pi = _participant_index(diagram, pid)
                if pi < 0:
                    continue
                if ev.position == "rightof" and pi < n - 1:
                    gap_mins[pi] = max(gap_mins[pi], note_width + 4)
                elif ev.position == "leftof" and pi > 0:
                    gap_mins[pi - 1] = max(gap_mins[pi - 1], note_width + 4)
            if ev.position == "over" and len(ev.participants) == 2:
                p1i = _participant_index(diagram, ev.participants[0])
                p2i = _participant_index(diagram, ev.participants[1])
                if p1i >= 0 and p2i >= 0:
                    lo, hi = min(p1i, p2i), max(p1i, p2i)
                    spans = hi - lo
                    per_gap = (note_width + spans - 1) // spans
                    for g in range(lo, hi):
                        gap_mins[g] = max(gap_mins[g], per_gap)
            continue

        eff = effective_labels[ev_idx]
        si = _participant_index(diagram, ev.source)
        ti = _participant_index(diagram, ev.target)
        if si < 0 or ti < 0 or si == ti:
            continue
        lo, hi = min(si, ti), max(si, ti)
        label_need = len(eff) + 6  # padding for arrow + spacing
        spans = hi - lo
        per_gap = (label_need + spans - 1) // spans
        for g in range(lo, hi):
            gap_mins[g] = max(gap_mins[g], per_gap)

    # Build center positions cumulatively
    col_centers = [0] * n
    col_centers[0] = box_widths[0] // 2 + 1  # left margin
    for i in range(1, n):
        col_centers[i] = col_centers[i - 1] + gap_mins[i - 1]

    # Account for self-messages extending to the right of a lifeline
    max_right = col_centers[-1] + box_widths[-1] // 2 + 2
    for ev in diagram.events:
        if isinstance(ev, Message):
            si = _participant_index(diagram, ev.source)
            ti = _participant_index(diagram, ev.target)
            if si >= 0 and si == ti:
                loop_width = max(len(ev.label) + 4, 8)
                needed = col_centers[si] + loop_width + 1
                max_right = max(max_right, needed)
        elif isinstance(ev, Note):
            # Notes to the right of the rightmost participant
            for pid in ev.participants:
                pi = _participant_index(diagram, pid)
                if pi >= 0 and ev.position == "rightof":
                    note_width = len(ev.text) + 4
                    needed = col_centers[pi] + 2 + note_width + 1
                    max_right = max(max_right, needed)

    # Compute row offsets (cumulative event heights)
    lifeline_start = _TOP_MARGIN + header_height
    row_offsets: list[int] = []
    cumulative = lifeline_start + 1
    for h in event_heights:
        row_offsets.append(cumulative)
        cumulative += h

    # Canvas dimensions
    canvas_width = max_right
    lifeline_end_row = cumulative
    canvas_height = lifeline_end_row + _BOTTOM_MARGIN

    return col_centers, box_widths, canvas_width, canvas_height, header_height, row_offsets


# ── Participant drawing functions ─────────────────────────────────

def _draw_actor(canvas: Canvas, cx: int, y: int, label: str, use_ascii: bool) -> None:
    """Draw a stick-figure actor, bottom-aligned to y + _ACTOR_HEIGHT - 1."""
    style = "node"
    canvas.put(y, cx, "O", merge=False, style=style)
    canvas.put(y + 1, cx - 1, "/", merge=False, style=style)
    canvas.put(y + 1, cx, "|", merge=False, style=style)
    canvas.put(y + 1, cx + 1, "\\", merge=False, style=style)
    canvas.put(y + 2, cx - 1, "/", merge=False, style=style)
    canvas.put(y + 2, cx + 1, "\\", merge=False, style=style)
    label_col = cx - len(label) // 2
    canvas.put_text(y + 4, label_col, label, style="label")


def _draw_database(canvas: Canvas, cx: int, y: int, width: int, label: str, cs: CharSet) -> None:
    """Draw a cylinder (database) participant."""
    bx = cx - width // 2
    draw_cylinder(canvas, bx, y, width, 5, label, cs, style="node")


def _draw_queue(canvas: Canvas, cx: int, y: int, width: int, label: str, cs: CharSet, use_ascii: bool) -> None:
    """Draw a queue participant — box with doubled right border."""
    bx = cx - width // 2
    style = "node"
    h = 5

    # Top border
    canvas.put(y, bx, cs.top_left, style=style)
    for c in range(bx + 1, bx + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, bx + width - 1, cs.round_top_right if not use_ascii else cs.top_right, style=style)

    # Bottom border
    canvas.put(y + h - 1, bx, cs.bottom_left, style=style)
    for c in range(bx + 1, bx + width - 1):
        canvas.put(y + h - 1, c, cs.horizontal, style=style)
    canvas.put(y + h - 1, bx + width - 1, cs.round_bottom_right if not use_ascii else cs.bottom_right, style=style)

    # Side borders
    for r in range(y + 1, y + h - 1):
        canvas.put(r, bx, cs.vertical, style=style)
        # Double right border
        if not use_ascii:
            canvas.put(r, bx + width - 1, "║", merge=False, style=style)
        else:
            canvas.put(r, bx + width - 1, cs.vertical, style=style)

    # Label centered
    label_col = bx + (width - len(label)) // 2
    label_row = y + h // 2
    canvas.put_text(label_row, label_col, label, style="label")


def _draw_boundary(canvas: Canvas, cx: int, y: int, label: str, cs: CharSet, use_ascii: bool) -> None:
    """Draw a boundary symbol: small box with horizontal bar extending left."""
    style = "node"
    # Small 3x3 box centered on cx
    box_left = cx - 1
    box_right = cx + 1

    # Top of box
    canvas.put(y, box_left, cs.top_left, style=style)
    canvas.put(y, cx, cs.horizontal, style=style)
    canvas.put(y, box_right, cs.top_right, style=style)

    # Middle row: bar extending left + box sides
    bar_start = cx - 3
    canvas.put(y + 1, bar_start, cs.horizontal, merge=False, style=style)
    canvas.put(y + 1, bar_start + 1, cs.horizontal, merge=False, style=style)
    canvas.put(y + 1, box_left, cs.tee_left if not use_ascii else cs.vertical, style=style)
    canvas.put(y + 1, cx, " ", merge=False, style=style)
    canvas.put(y + 1, box_right, cs.vertical, style=style)

    # Bottom of box
    canvas.put(y + 2, box_left, cs.bottom_left, style=style)
    canvas.put(y + 2, cx, cs.horizontal, style=style)
    canvas.put(y + 2, box_right, cs.bottom_right, style=style)

    # Label below
    label_col = cx - len(label) // 2
    canvas.put_text(y + 4, label_col, label, style="label")


def _draw_control(canvas: Canvas, cx: int, y: int, label: str, cs: CharSet, use_ascii: bool) -> None:
    """Draw a control symbol: small circle with arrowhead above."""
    style = "node"
    # Arrowhead
    if use_ascii:
        canvas.put(y, cx, "<", merge=False, style=style)
    else:
        canvas.put(y, cx, "◁", merge=False, style=style)

    # Small rounded box
    canvas.put(y + 1, cx - 1, cs.round_top_left if not use_ascii else cs.top_left, style=style)
    canvas.put(y + 1, cx, cs.horizontal, style=style)
    canvas.put(y + 1, cx + 1, cs.round_top_right if not use_ascii else cs.top_right, style=style)
    canvas.put(y + 2, cx - 1, cs.round_bottom_left if not use_ascii else cs.bottom_left, style=style)
    canvas.put(y + 2, cx, cs.horizontal, style=style)
    canvas.put(y + 2, cx + 1, cs.round_bottom_right if not use_ascii else cs.bottom_right, style=style)

    # Label below
    label_col = cx - len(label) // 2
    canvas.put_text(y + 4, label_col, label, style="label")


def _draw_entity(canvas: Canvas, cx: int, y: int, label: str, cs: CharSet, use_ascii: bool) -> None:
    """Draw an entity symbol: small circle with underline."""
    style = "node"
    # Small rounded box
    canvas.put(y, cx - 1, cs.round_top_left if not use_ascii else cs.top_left, style=style)
    canvas.put(y, cx, cs.horizontal, style=style)
    canvas.put(y, cx + 1, cs.round_top_right if not use_ascii else cs.top_right, style=style)
    canvas.put(y + 1, cx - 1, cs.round_bottom_left if not use_ascii else cs.bottom_left, style=style)
    canvas.put(y + 1, cx, cs.horizontal, style=style)
    canvas.put(y + 1, cx + 1, cs.round_bottom_right if not use_ascii else cs.bottom_right, style=style)

    # Underline
    canvas.put(y + 2, cx - 1, cs.horizontal, merge=False, style=style)
    canvas.put(y + 2, cx, cs.horizontal, merge=False, style=style)
    canvas.put(y + 2, cx + 1, cs.horizontal, merge=False, style=style)

    # Label below
    label_col = cx - len(label) // 2
    canvas.put_text(y + 4, label_col, label, style="label")


def _draw_collections(canvas: Canvas, cx: int, y: int, width: int, label: str, cs: CharSet, use_ascii: bool) -> None:
    """Draw a collections symbol: two overlapping rectangles."""
    style = "node"
    bx = cx - width // 2
    h = 5

    # Back rectangle (offset +1 right, 0 up) — just top and right edges visible
    # Top edge of back rectangle
    for c in range(bx + 2, bx + width + 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, bx + 1, cs.top_left, style=style)
    canvas.put(y, bx + width, cs.top_right, style=style)
    # Right edge of back rectangle
    canvas.put(y + 1, bx + width, cs.vertical, style=style)

    # Front rectangle
    canvas.put(y + 1, bx, cs.top_left, style=style)
    for c in range(bx + 1, bx + width - 1):
        canvas.put(y + 1, c, cs.horizontal, style=style)
    # Top-right corner of front connects to back rect's right edge
    canvas.put(y + 1, bx + width - 1, cs.top_right, style=style)

    # Bottom of back rect merges with top-right of front
    canvas.put(y + 2, bx + width, cs.bottom_right, style=style)
    for c in range(bx + width - 1, bx + width):
        pass  # handled by junction merging

    # Side borders of front
    for r in range(y + 2, y + h - 1):
        canvas.put(r, bx, cs.vertical, style=style)
        canvas.put(r, bx + width - 1, cs.vertical, style=style)

    # Bottom border of back rect stub
    canvas.put(y + 2, bx + width - 1, cs.tee_left if not use_ascii else cs.vertical, style=style)
    canvas.put(y + 2, bx + width, cs.bottom_right, style=style)

    # Bottom border of front
    canvas.put(y + h - 1, bx, cs.bottom_left, style=style)
    for c in range(bx + 1, bx + width - 1):
        canvas.put(y + h - 1, c, cs.horizontal, style=style)
    canvas.put(y + h - 1, bx + width - 1, cs.bottom_right, style=style)

    # Label centered in front rectangle
    label_col = bx + (width - len(label)) // 2
    label_row = y + 1 + (h - 1) // 2
    canvas.put_text(label_row, label_col, label, style="label")


def _draw_participant_header(
    canvas: Canvas, cx: int, bw: int, header_height: int,
    participant, cs: CharSet, use_ascii: bool,
) -> None:
    """Dispatch to the correct participant drawing function."""
    kind = participant.kind
    label = participant.label

    if kind == "actor":
        actor_y = _TOP_MARGIN + (header_height - _ACTOR_HEIGHT)
        _draw_actor(canvas, cx, actor_y, label, use_ascii)
    elif kind == "database":
        db_y = _TOP_MARGIN + (header_height - 5)
        _draw_database(canvas, cx, db_y, bw, label, cs)
    elif kind == "queue":
        q_y = _TOP_MARGIN + (header_height - 5)
        _draw_queue(canvas, cx, q_y, bw, label, cs, use_ascii)
    elif kind == "boundary":
        b_y = _TOP_MARGIN + (header_height - 5)
        _draw_boundary(canvas, cx, b_y, label, cs, use_ascii)
    elif kind == "control":
        c_y = _TOP_MARGIN + (header_height - 5)
        _draw_control(canvas, cx, c_y, label, cs, use_ascii)
    elif kind == "entity":
        e_y = _TOP_MARGIN + (header_height - 5)
        _draw_entity(canvas, cx, e_y, label, cs, use_ascii)
    elif kind == "collections":
        col_y = _TOP_MARGIN + (header_height - 5)
        _draw_collections(canvas, cx, col_y, bw, label, cs, use_ascii)
    else:
        # Default: participant box
        box_y = _TOP_MARGIN + (header_height - _BOX_HEIGHT)
        bx = cx - bw // 2
        draw_rectangle(canvas, bx, box_y, bw, _BOX_HEIGHT, label, cs, style="node")


def render_sequence(diagram: SequenceDiagram, *, use_ascii: bool = False) -> Canvas:
    """Render a SequenceDiagram to a Canvas."""
    cs = ASCII if use_ascii else UNICODE

    col_centers, box_widths, width, height, header_height, row_offsets = _compute_layout(
        diagram, diagram.autonumber
    )
    if width == 0:
        return Canvas(1, 1)

    canvas = Canvas(width, height)

    # ── 1. Draw participant headers at top ────────────────────────
    for i, p in enumerate(diagram.participants):
        cx = col_centers[i]
        bw = box_widths[i]
        _draw_participant_header(canvas, cx, bw, header_height, p, cs, use_ascii)

    # ── 2. Draw lifelines ─────────────────────────────────────────
    lifeline_start = _TOP_MARGIN + header_height
    lifeline_end = height - _BOTTOM_MARGIN - 1
    lifeline_char = ":" if use_ascii else "┆"
    for i in range(len(diagram.participants)):
        cx = col_centers[i]
        for r in range(lifeline_start, lifeline_end + 1):
            canvas.put(r, cx, lifeline_char, merge=False, style="edge")

    # ── 3. Draw events (messages and notes) ───────────────────────
    msg_counter = 0
    for idx, ev in enumerate(diagram.events):
        row = row_offsets[idx]

        if isinstance(ev, Note):
            _draw_note(canvas, ev, row, col_centers, diagram, cs, use_ascii)
            continue

        # It's a Message
        msg_counter += 1
        display_label = _effective_label(ev, msg_counter if diagram.autonumber else None)

        si = _participant_index(diagram, ev.source)
        ti = _participant_index(diagram, ev.target)
        if si < 0 or ti < 0:
            continue

        if si == ti:
            _draw_self_message(canvas, col_centers[si], row, ev, display_label, cs, use_ascii)
        else:
            _draw_message(canvas, col_centers[si], col_centers[ti], row, ev, display_label, cs, use_ascii)

    return canvas


def _draw_note(
    canvas: Canvas,
    note: Note,
    row: int,
    col_centers: list[int],
    diagram: SequenceDiagram,
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a note box at the given row."""
    note_width = len(note.text) + 4
    note_height = 3

    # Determine horizontal placement
    if note.position == "rightof":
        pi = _participant_index(diagram, note.participants[0])
        if pi < 0:
            return
        note_x = col_centers[pi] + 2
    elif note.position == "leftof":
        pi = _participant_index(diagram, note.participants[0])
        if pi < 0:
            return
        note_x = col_centers[pi] - 2 - note_width
    elif note.position == "over":
        if len(note.participants) == 2:
            p1i = _participant_index(diagram, note.participants[0])
            p2i = _participant_index(diagram, note.participants[1])
            if p1i < 0 or p2i < 0:
                return
            center = (col_centers[p1i] + col_centers[p2i]) // 2
            # Ensure spanning note covers both lifelines
            span_width = abs(col_centers[p1i] - col_centers[p2i]) + 4
            note_width = max(note_width, span_width)
        else:
            pi = _participant_index(diagram, note.participants[0])
            if pi < 0:
                return
            center = col_centers[pi]
        note_x = center - note_width // 2
    else:
        return

    # Clamp note_x to 0
    note_x = max(0, note_x)

    # Clear the interior so lifeline chars don't bleed through
    for r in range(row, row + note_height):
        for c in range(note_x, note_x + note_width):
            if 0 <= r < canvas.height and 0 <= c < canvas.width:
                canvas._grid[r][c] = " "

    draw_rectangle(canvas, note_x, row, note_width, note_height, note.text, cs, style="node")


def _draw_message(
    canvas: Canvas,
    src_col: int,
    tgt_col: int,
    row: int,
    msg: Message,
    display_label: str,
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a horizontal message arrow between two lifelines."""
    left = min(src_col, tgt_col)
    right = max(src_col, tgt_col)
    going_right = tgt_col > src_col

    # Line character
    if msg.line_type == "dotted":
        h_char = "." if use_ascii else "┄"
    else:
        h_char = "-" if use_ascii else "─"

    # Draw the line (excluding endpoints which are lifeline chars)
    for c in range(left + 1, right):
        canvas.put(row, c, h_char, merge=False, style="edge")

    # Arrowhead at target
    if msg.arrow_type == "bidirectional":
        # Arrowheads at both ends
        if use_ascii:
            canvas.put(row, left, "<", merge=False, style="arrow")
            canvas.put(row, right, ">", merge=False, style="arrow")
        else:
            canvas.put(row, left, "◄", merge=False, style="arrow")
            canvas.put(row, right, "►", merge=False, style="arrow")
    elif msg.arrow_type == "arrow":
        if going_right:
            arrow = ">" if use_ascii else "►"
            canvas.put(row, right, arrow, merge=False, style="arrow")
            canvas.put(row, left, h_char, merge=False, style="edge")
        else:
            arrow = "<" if use_ascii else "◄"
            canvas.put(row, left, arrow, merge=False, style="arrow")
            canvas.put(row, right, h_char, merge=False, style="edge")
    elif msg.arrow_type == "cross":
        if going_right:
            canvas.put(row, right, "x", merge=False, style="arrow")
            canvas.put(row, left, h_char, merge=False, style="edge")
        else:
            canvas.put(row, left, "x", merge=False, style="arrow")
            canvas.put(row, right, h_char, merge=False, style="edge")
    elif msg.arrow_type == "async":
        if going_right:
            canvas.put(row, right, ")", merge=False, style="arrow")
            canvas.put(row, left, h_char, merge=False, style="edge")
        else:
            canvas.put(row, left, "(", merge=False, style="arrow")
            canvas.put(row, right, h_char, merge=False, style="edge")
    else:
        # "open" — no arrowhead, just line to endpoints
        canvas.put(row, left, h_char, merge=False, style="edge")
        canvas.put(row, right, h_char, merge=False, style="edge")

    # Label above the line
    if display_label:
        label_row = row - 1
        label_col = left + 2
        canvas.put_text(label_row, label_col, display_label, style="edge_label")


def _draw_self_message(
    canvas: Canvas,
    col: int,
    row: int,
    msg: Message,
    display_label: str,
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a self-referencing message (loop to the right)."""
    loop_width = max(len(display_label) + 4, 8)

    if msg.line_type == "dotted":
        h_char = "." if use_ascii else "┄"
        v_char = ":" if use_ascii else "┆"
    else:
        h_char = "-" if use_ascii else "─"
        v_char = "|" if use_ascii else "│"

    # Top horizontal line going right
    for c in range(col + 1, col + loop_width):
        canvas.put(row, c, h_char, merge=False, style="edge")

    # Vertical line going down
    right_col = col + loop_width - 1
    canvas.put(row + 1, right_col, v_char, merge=False, style="edge")

    # Bottom horizontal line going left back to lifeline
    for c in range(col + 1, col + loop_width):
        canvas.put(row + 1, c, h_char, merge=False, style="edge")

    # Arrowhead pointing back at lifeline
    if msg.arrow_type == "arrow":
        arrow = "<" if use_ascii else "◄"
        canvas.put(row + 1, col, arrow, merge=False, style="arrow")
    elif msg.arrow_type == "cross":
        canvas.put(row + 1, col, "x", merge=False, style="arrow")
    elif msg.arrow_type == "async":
        canvas.put(row + 1, col, "(", merge=False, style="arrow")
    else:
        canvas.put(row + 1, col, h_char, merge=False, style="edge")

    # Corners
    if not use_ascii:
        canvas.put(row, right_col, "┐", merge=False, style="edge")
        canvas.put(row + 1, right_col, "┘", merge=False, style="edge")
    else:
        canvas.put(row, right_col, "+", merge=False, style="edge")
        canvas.put(row + 1, right_col, "+", merge=False, style="edge")

    # Label above the top line
    if display_label:
        canvas.put_text(row - 1, col + 2, display_label, style="edge_label")
