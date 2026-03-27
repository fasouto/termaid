"""Renderer for sequence diagrams.

Renders a SequenceDiagram directly to a Canvas, bypassing the grid layout
and A* edge routing used by flowcharts.
"""
from __future__ import annotations

from ..model.sequence import ActivateEvent, Block, BlockSection, DestroyEvent, Message, Note, SequenceDiagram
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from .shapes import draw_rectangle, draw_cylinder
from ..utils import display_width


# ── layout constants ──────────────────────────────────────────────
_BOX_PAD = 4          # horizontal padding inside participant boxes
_BOX_HEIGHT = 3       # participant box height
_ACTOR_HEIGHT = 5     # actor stick-figure height (head, body, legs, gap, label)
_MIN_GAP = 16         # minimum gap between participant centers
_EVENT_ROW_H = 2      # rows per message event
_NOTE_ROW_H = 4       # rows per note event (3-row box + 1 gap)
_BLOCK_START_H = 3    # rows for block start (border + label + gap)
_BLOCK_SECTION_H = 2  # rows for section break (dashed line + gap)
_BLOCK_END_H = 2      # rows for block end (bottom border + gap)
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


# ── Sentinel types for flattened events ──────────────────────────
class _BlockStart:
    """Marker for block start in flattened event list."""
    def __init__(self, block: Block, depth: int) -> None:
        self.block = block
        self.depth = depth

class _BlockSectionBreak:
    """Marker for else/and section in flattened event list."""
    def __init__(self, section: BlockSection, depth: int) -> None:
        self.section = section
        self.depth = depth

class _BlockEnd:
    """Marker for block end in flattened event list."""
    def __init__(self, block: Block, depth: int) -> None:
        self.block = block
        self.depth = depth


def _flatten_events(events: list, depth: int = 0) -> list:
    """Recursively flatten Block events into a linear list with boundary markers."""
    result = []
    for ev in events:
        if isinstance(ev, Block):
            result.append(_BlockStart(ev, depth))
            result.extend(_flatten_events(ev.events, depth + 1))
            for section in ev.sections:
                result.append(_BlockSectionBreak(section, depth))
                result.extend(_flatten_events(section.events, depth + 1))
            result.append(_BlockEnd(ev, depth))
        elif isinstance(ev, ActivateEvent):
            # ActivateEvents don't take a row; processed separately
            result.append(ev)
        else:
            result.append(ev)
    return result


def _note_lines(note: Note) -> list[str]:
    """Split note text into lines."""
    return note.text.split("\n") if "\n" in note.text else [note.text]


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
    flat_events: list,
    padding_x: int = _BOX_PAD,
    min_gap: int = _MIN_GAP,
) -> tuple[list[int], list[int], int, int, int, list[int]]:
    """Compute column center positions and box widths.

    Returns (col_centers, box_widths, canvas_width, canvas_height, header_height, row_offsets).
    """
    n = len(diagram.participants)
    if n == 0:
        return [], [], 0, 0, 0, []

    # Box widths based on label length
    box_widths = [max(display_width(p.label) + padding_x, 12) for p in diagram.participants]

    # Header height: tallest participant kind
    header_height = max(_KIND_HEIGHT.get(p.kind, 3) for p in diagram.participants)

    # Compute per-event heights and effective labels for gap computation
    event_heights: list[int] = []
    effective_labels: list[str] = []
    msg_counter = 0
    for ev in flat_events:
        if isinstance(ev, ActivateEvent):
            # No row needed
            event_heights.append(0)
            effective_labels.append("")
        elif isinstance(ev, DestroyEvent):
            event_heights.append(_EVENT_ROW_H)
            effective_labels.append("")
        elif isinstance(ev, Note):
            lines = _note_lines(ev)
            note_h = len(lines) + 2 + 1  # border top + content lines + border bottom + gap
            event_heights.append(note_h)
            effective_labels.append("")
        elif isinstance(ev, _BlockStart):
            event_heights.append(_BLOCK_START_H)
            effective_labels.append("")
        elif isinstance(ev, _BlockSectionBreak):
            event_heights.append(_BLOCK_SECTION_H)
            effective_labels.append("")
        elif isinstance(ev, _BlockEnd):
            event_heights.append(_BLOCK_END_H)
            effective_labels.append("")
        elif isinstance(ev, Message):
            msg_counter += 1
            eff = _effective_label(ev, msg_counter if autonumber else None)
            effective_labels.append(eff)
            event_heights.append(_EVENT_ROW_H)
        else:
            event_heights.append(0)
            effective_labels.append("")

    # Compute per-gap minimum widths based on message labels between adjacent pairs
    gap_mins = [min_gap] * (n - 1) if n > 1 else []
    for ev_idx, ev in enumerate(flat_events):
        if isinstance(ev, Note):
            # Notes may need gap expansion
            lines = _note_lines(ev)
            note_width = max(display_width(line) for line in lines) + 4
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

        if not isinstance(ev, Message):
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
    for ev in flat_events:
        if isinstance(ev, Message):
            si = _participant_index(diagram, ev.source)
            ti = _participant_index(diagram, ev.target)
            if si >= 0 and si == ti:
                loop_width = max(display_width(ev.label) + 4, 8)
                needed = col_centers[si] + loop_width + 1
                max_right = max(max_right, needed)
        elif isinstance(ev, Note):
            # Notes to the right of the rightmost participant
            for pid in ev.participants:
                pi = _participant_index(diagram, pid)
                if pi >= 0 and ev.position == "rightof":
                    lines = _note_lines(ev)
                    note_width = max(display_width(line) for line in lines) + 4
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
    label_col = cx - display_width(label) // 2
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
    label_col = bx + (width - display_width(label)) // 2
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
    label_col = cx - display_width(label) // 2
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
    label_col = cx - display_width(label) // 2
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
    label_col = cx - display_width(label) // 2
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
    label_col = bx + (width - display_width(label)) // 2
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


def _compute_activation_ranges(flat_events: list, row_offsets: list[int]) -> dict[str, list[tuple[int, int]]]:
    """Compute activation ranges per participant from flattened events.

    Returns {participant_id: [(start_row, end_row), ...]}.
    """
    # Track open activations per participant
    open_activations: dict[str, list[int]] = {}  # pid -> [start_rows...]
    ranges: dict[str, list[tuple[int, int]]] = {}

    for idx, ev in enumerate(flat_events):
        if not isinstance(ev, ActivateEvent):
            continue
        row = row_offsets[idx]
        pid = ev.participant
        if ev.active:
            open_activations.setdefault(pid, []).append(row)
        else:
            # Close the most recent activation
            if pid in open_activations and open_activations[pid]:
                start = open_activations[pid].pop()
                ranges.setdefault(pid, []).append((start, row))

    # Close any still-open activations at the last row
    max_row = max(row_offsets) + 1 if row_offsets else 0
    for pid, starts in open_activations.items():
        for start in starts:
            ranges.setdefault(pid, []).append((start, max_row))

    return ranges


def _is_activated(ranges: dict[str, list[tuple[int, int]]], pid: str, row: int) -> bool:
    """Check if a participant is activated at a given row."""
    for start, end in ranges.get(pid, []):
        if start <= row <= end:
            return True
    return False


def render_sequence(diagram: SequenceDiagram, *, use_ascii: bool = False, padding_x: int = 4, gap: int = 16) -> Canvas:
    """Render a SequenceDiagram to a Canvas."""
    cs = ASCII if use_ascii else UNICODE

    # Flatten events for linear layout
    flat_events = _flatten_events(diagram.events)

    col_centers, box_widths, width, height, header_height, row_offsets = _compute_layout(
        diagram, diagram.autonumber, flat_events, padding_x=padding_x, min_gap=gap
    )
    if width == 0:
        return Canvas(1, 1)

    canvas = Canvas(width, height)

    # Compute activation ranges
    activation_ranges = _compute_activation_ranges(flat_events, row_offsets)

    # ── 1. Draw participant headers at top ────────────────────────
    for i, p in enumerate(diagram.participants):
        cx = col_centers[i]
        bw = box_widths[i]
        _draw_participant_header(canvas, cx, bw, header_height, p, cs, use_ascii)

    # ── Compute destroyed participants and their destruction rows ──
    destroyed: dict[str, int] = {}  # participant -> row where destroyed
    for idx, ev in enumerate(flat_events):
        if isinstance(ev, DestroyEvent) and ev.participant not in destroyed:
            destroyed[ev.participant] = row_offsets[idx]

    # ── 2. Draw lifelines ─────────────────────────────────────────
    lifeline_start = _TOP_MARGIN + header_height
    lifeline_end = height - _BOTTOM_MARGIN - 1
    lifeline_char = ":" if use_ascii else "┆"
    active_char = "[" if use_ascii else "║"
    for i, p in enumerate(diagram.participants):
        cx = col_centers[i]
        end_row = destroyed.get(p.id, lifeline_end + 1)
        for r in range(lifeline_start, min(end_row, lifeline_end + 1)):
            if _is_activated(activation_ranges, p.id, r):
                canvas.put(r, cx, active_char, merge=False, style="edge")
            else:
                canvas.put(r, cx, lifeline_char, merge=False, style="edge")

    # ── 2.5 Draw continuous block side borders ─────────────────────
    block_border_stack: list[tuple[int, int, int]] = []  # (left, right, start_row)
    for idx, ev in enumerate(flat_events):
        row = row_offsets[idx]
        if isinstance(ev, _BlockStart):
            left, right = _block_frame_bounds(col_centers, ev.depth)
            block_border_stack.append((left, right, row))
        elif isinstance(ev, _BlockEnd):
            if block_border_stack:
                left, right, start_row = block_border_stack.pop()
                for r in range(start_row + 1, row):
                    canvas.put(r, left, cs.vertical, merge=False, style="node")
                    if right < canvas.width:
                        canvas.put(r, right, cs.vertical, merge=False, style="node")

    # ── 3. Draw events (messages, notes, blocks) ──────────────────
    msg_counter = 0
    for idx, ev in enumerate(flat_events):
        row = row_offsets[idx]

        if isinstance(ev, ActivateEvent):
            # No visual output needed (lifeline already handles it)
            continue

        if isinstance(ev, DestroyEvent):
            pi = _participant_index(diagram, ev.participant)
            if pi >= 0:
                cx = col_centers[pi]
                x_char = "X" if use_ascii else "╳"
                canvas.put(row, cx, x_char, merge=False, style="arrow")
            continue

        if isinstance(ev, Note):
            _draw_note(canvas, ev, row, col_centers, diagram, cs, use_ascii)
            continue

        if isinstance(ev, _BlockStart):
            _draw_block_start(canvas, ev, row, col_centers, cs, use_ascii)
            continue

        if isinstance(ev, _BlockSectionBreak):
            _draw_block_section(canvas, ev, row, col_centers, cs, use_ascii)
            continue

        if isinstance(ev, _BlockEnd):
            _draw_block_end(canvas, ev, row, col_centers, cs, use_ascii)
            continue

        if isinstance(ev, Message):
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


# ── Block frame drawing ──────────────────────────────────────────

def _block_frame_bounds(col_centers: list[int], depth: int) -> tuple[int, int]:
    """Compute left and right columns for block frame at given nesting depth."""
    indent = depth * 2
    left = max(0, col_centers[0] - 6 + indent) if col_centers else indent
    right = (col_centers[-1] + 6 - indent) if col_centers else 20 - indent
    return left, right


def _draw_block_start(
    canvas: Canvas,
    ev: _BlockStart,
    row: int,
    col_centers: list[int],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw the top border of a block frame with kind label."""
    left, right = _block_frame_bounds(col_centers, ev.depth)
    h_char = cs.horizontal
    style = "node"

    # Top border
    canvas.put(row, left, cs.top_left, merge=False, style=style)
    for c in range(left + 1, min(right, canvas.width)):
        canvas.put(row, c, h_char, merge=False, style=style)
    if right < canvas.width:
        canvas.put(row, right, cs.top_right, merge=False, style=style)

    # Label row: [kind] label — clear interior first to hide lifeline chars
    label = f"[{ev.block.kind}] {ev.block.label}" if ev.block.label else f"[{ev.block.kind}]"
    label_col = left + 1
    if row + 1 < canvas.height:
        canvas.put(row + 1, left, cs.vertical, merge=False, style=style)
        for c in range(left + 1, min(right, canvas.width)):
            canvas._grid[row + 1][c] = " "
        if right < canvas.width:
            canvas.put(row + 1, right, cs.vertical, merge=False, style=style)
        canvas.put_text(row + 1, label_col, label, style="edge_label")


def _draw_block_section(
    canvas: Canvas,
    ev: _BlockSectionBreak,
    row: int,
    col_centers: list[int],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a dashed horizontal divider for else/and sections."""
    left, right = _block_frame_bounds(col_centers, ev.depth)
    dash = "." if use_ascii else "┄"
    style = "node"

    canvas.put(row, left, cs.vertical, merge=False, style=style)
    for c in range(left + 1, min(right, canvas.width)):
        canvas.put(row, c, dash, merge=False, style=style)
    if right < canvas.width:
        canvas.put(row, right, cs.vertical, merge=False, style=style)

    # Section label after left border
    if ev.section.label:
        canvas.put_text(row, left + 2, f"[{ev.section.label}]", style="edge_label")


def _draw_block_end(
    canvas: Canvas,
    ev: _BlockEnd,
    row: int,
    col_centers: list[int],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw the bottom border of a block frame."""
    left, right = _block_frame_bounds(col_centers, ev.depth)
    h_char = cs.horizontal
    style = "node"

    canvas.put(row, left, cs.bottom_left, merge=False, style=style)
    for c in range(left + 1, min(right, canvas.width)):
        canvas.put(row, c, h_char, merge=False, style=style)
    if right < canvas.width:
        canvas.put(row, right, cs.bottom_right, merge=False, style=style)


# ── Note drawing ─────────────────────────────────────────────────

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
    lines = _note_lines(note)
    note_width = max(display_width(line) for line in lines) + 4
    note_height = len(lines) + 2

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


# ── Message drawing ──────────────────────────────────────────────

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
    loop_width = max(display_width(display_label) + 4, 8)

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
