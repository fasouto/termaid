"""Renderer for sequence diagrams.

Renders a SequenceDiagram directly to a Canvas, bypassing the grid layout
and A* edge routing used by flowcharts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from ..model.sequence import ActivateEvent, Block, BlockSection, DestroyEvent, Event, Message, Note, SequenceDiagram
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet
from .shapes import draw_rectangle, draw_cylinder
from ..utils import display_width, wrap_display_text


# ── layout constants ──────────────────────────────────────────────
_BOX_PAD = 4          # horizontal padding inside participant boxes
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
    def __init__(self, section: BlockSection, block: Block, depth: int) -> None:
        self.block = block
        self.section = section
        self.depth = depth

class _BlockEnd:
    """Marker for block end in flattened event list."""
    def __init__(self, block: Block, depth: int) -> None:
        self.block = block
        self.depth = depth


_FlatEvent = Union[Event, _BlockStart, _BlockSectionBreak, _BlockEnd]


def _flatten_events(events: list[Event], depth: int = 0) -> list[_FlatEvent]:
    """Recursively flatten Block events into a linear list with boundary markers."""
    result: list[_FlatEvent] = []
    for ev in events:
        if isinstance(ev, Block):
            result.append(_BlockStart(ev, depth))
            result.extend(_flatten_events(ev.events, depth + 1))
            for section in ev.sections:
                result.append(_BlockSectionBreak(section, ev, depth))
                result.extend(_flatten_events(section.events, depth + 1))
            result.append(_BlockEnd(ev, depth))
        elif isinstance(ev, ActivateEvent):
            # ActivateEvents don't take a row; processed separately
            result.append(ev)
        else:
            result.append(ev)
    return result


@dataclass
class _Labels:
    """Every string the renderer draws, split into display lines.

    Built once per render so gap minimums, self-loop widths, frame bounds,
    row heights and drawing all read the same lines.
    """
    participants: list[list[str]]
    events: list[list[str]]  # message label or note lines per flat event, [] otherwise
    block_titles: dict[int, list[str]] = field(default_factory=dict)  # id(block) -> "[kind] label" lines
    sections: dict[int, list[str]] = field(default_factory=dict)  # id(section) -> "[label]" lines


def _lines_width(lines: list[str]) -> int:
    return max((display_width(line) for line in lines), default=0)


def _extra_rows(lines: list[str]) -> int:
    """Rows a label needs beyond the single line the base event height holds."""
    return max(len(lines), 1) - 1


def _self_loop_width(lines: list[str]) -> int:
    return max(_lines_width(lines) + 4, 8)


def _participant_height(participant, lines: list[str]) -> int:
    return _KIND_HEIGHT.get(participant.kind, 3) + len(lines) - 1


def _collect_labels(diagram: SequenceDiagram, flat_events: list[_FlatEvent], max_label_width: int | None) -> _Labels:
    def wrap(text: str) -> list[str]:
        return [text] if max_label_width is None else wrap_display_text(text, max_label_width)

    events: list[list[str]] = []
    msg_counter = 0
    for ev in flat_events:
        if isinstance(ev, Message):
            msg_counter += 1
            eff = _effective_label(ev, msg_counter if diagram.autonumber else None)
            events.append(wrap(eff) if eff else [])
        elif isinstance(ev, Note):
            events.append(ev.text.split("\n") if max_label_width is None else wrap(ev.text))
        else:
            events.append([])
    return _Labels([wrap(p.label) for p in diagram.participants], events)


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
    flat_events: list[_FlatEvent],
    labels: _Labels,
    padding_x: int = _BOX_PAD,
    min_gap: int = _MIN_GAP,
    wrap_scope_labels: bool = False,
) -> tuple[list[int], list[int], int, int, int, list[int], dict[int, tuple[int, int]]]:
    """Compute column center positions and box widths.

    Fills ``labels.block_titles`` and ``labels.sections`` while measuring frames.
    Returns (col_centers, box_widths, canvas_width, canvas_height, header_height, row_offsets, block_bounds).
    """
    n = len(diagram.participants)
    if n == 0:
        return [], [], 0, 0, 0, [], {}

    box_widths = [_lines_width(lines) + padding_x + 2 for lines in labels.participants]  # +2 for borders

    header_height = max(
        _participant_height(p, lines) for p, lines in zip(diagram.participants, labels.participants)
    )

    # Compute per-gap minimum widths based on message labels between adjacent pairs
    gap_mins = [min_gap] * (n - 1) if n > 1 else []

    # Ensure gaps are wide enough that participant boxes don't overlap
    for i in range(n - 1):
        box_gap_need = (box_widths[i] + box_widths[i + 1]) // 2 + 2
        gap_mins[i] = max(gap_mins[i], box_gap_need)

    for ev_idx, ev in enumerate(flat_events):
        if isinstance(ev, Note):
            # Notes may need gap expansion
            note_width = _lines_width(labels.events[ev_idx]) + 4
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

        si = _participant_index(diagram, ev.source)
        ti = _participant_index(diagram, ev.target)
        if si < 0 or ti < 0 or si == ti:
            continue
        lo, hi = min(si, ti), max(si, ti)
        label_need = _lines_width(labels.events[ev_idx]) + 6  # padding for arrow + spacing
        spans = hi - lo
        per_gap = (label_need + spans - 1) // spans
        for g in range(lo, hi):
            gap_mins[g] = max(gap_mins[g], per_gap)

    # Build center positions cumulatively
    col_centers = [0] * n
    col_centers[0] = box_widths[0] // 2 + 1  # left margin
    for i in range(1, n):
        col_centers[i] = col_centers[i - 1] + gap_mins[i - 1]

    # Account for self-messages and notes extending beyond participant headers.
    max_right = col_centers[-1] + box_widths[-1] // 2 + 2
    for event_index, event in enumerate(flat_events):
        if isinstance(event, Message) and event.source == event.target:
            source_index = _participant_index(diagram, event.source)
            if source_index >= 0:
                loop_width = _self_loop_width(labels.events[event_index])
                max_right = max(max_right, col_centers[source_index] + loop_width + 1)
        elif isinstance(event, Note):
            note_bounds = _note_bounds(event, labels.events[event_index], col_centers, diagram)
            if note_bounds is not None:
                note_left, note_right = note_bounds
                # Notes outside a scope retain the drawing path's edge clamping.
                note_width = note_right - note_left + 1
                max_right = max(max_right, max(0, note_left) + note_width + 1)

    # Measure scopes from their contents, then reserve enough space on both sides.
    # Moving lifelines together preserves message geometry and keeps outer frames
    # outside their children even when the first participant is near column zero.
    raw_block_bounds = _compute_block_bounds(diagram, flat_events, col_centers, labels, wrap_scope_labels)
    left_shift = max(0, -min((left for left, _ in raw_block_bounds.values()), default=0))
    shifted_centers = [center + left_shift for center in col_centers]
    block_bounds = {
        block_id: (left + left_shift, right + left_shift)
        for block_id, (left, right) in raw_block_bounds.items()
    }
    framed_right = max((right + 1 for _, right in block_bounds.values()), default=0)

    # Row offsets: cumulative event heights, each grown by its label's extra lines
    lifeline_start = _TOP_MARGIN + header_height
    row_offsets: list[int] = []
    cumulative = lifeline_start + 1
    for idx, ev in enumerate(flat_events):
        row_offsets.append(cumulative)
        lines = labels.events[idx]
        if isinstance(ev, ActivateEvent):
            continue
        if isinstance(ev, DestroyEvent):
            cumulative += _EVENT_ROW_H
        elif isinstance(ev, Note):
            cumulative += len(lines) + 2 + 1  # border top + content lines + border bottom + gap
        elif isinstance(ev, _BlockStart):
            cumulative += _BLOCK_START_H + _extra_rows(labels.block_titles[id(ev.block)])
        elif isinstance(ev, _BlockSectionBreak):
            cumulative += _BLOCK_SECTION_H + _extra_rows(labels.sections[id(ev.section)])
        elif isinstance(ev, _BlockEnd):
            cumulative += _BLOCK_END_H
        elif isinstance(ev, Message):
            # Self-messages draw a 2-row loop below the label rows
            loop_rows = 1 if ev.source == ev.target else 0
            cumulative += _EVENT_ROW_H + loop_rows + _extra_rows(lines)

    # Canvas dimensions
    canvas_width = max(max_right + left_shift, framed_right)
    lifeline_end_row = cumulative
    canvas_height = lifeline_end_row + _BOTTOM_MARGIN

    return shifted_centers, box_widths, canvas_width, canvas_height, header_height, row_offsets, block_bounds


# ── Participant drawing functions ─────────────────────────────────

def _put_centered_lines(canvas: Canvas, start_row: int, cx: int, lines: list[str]) -> None:
    for offset, line in enumerate(lines):
        canvas.put_text(start_row + offset, cx - display_width(line) // 2, line, style="label")


def _draw_actor(canvas: Canvas, cx: int, y: int, lines: list[str], use_ascii: bool) -> None:
    """Draw a stick-figure actor; the label lines start at y + 4."""
    style = "node"
    canvas.put(y, cx, "O", merge=False, style=style)
    canvas.put(y + 1, cx - 1, "/", merge=False, style=style)
    canvas.put(y + 1, cx, "|", merge=False, style=style)
    canvas.put(y + 1, cx + 1, "\\", merge=False, style=style)
    canvas.put(y + 2, cx - 1, "/", merge=False, style=style)
    canvas.put(y + 2, cx + 1, "\\", merge=False, style=style)
    _put_centered_lines(canvas, y + 4, cx, lines)


def _draw_database(canvas: Canvas, cx: int, y: int, width: int, h: int, lines: list[str], cs: CharSet) -> None:
    """Draw a cylinder (database) participant."""
    bx = cx - width // 2
    draw_cylinder(canvas, bx, y, width, h, "\n".join(lines), cs, style="node")


def _draw_queue(canvas: Canvas, cx: int, y: int, width: int, h: int, lines: list[str], cs: CharSet, use_ascii: bool) -> None:
    """Draw a queue participant — box with doubled right border."""
    bx = cx - width // 2
    style = "node"

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

    _put_centered_lines(canvas, y + (h - len(lines)) // 2, cx, lines)


def _draw_boundary(canvas: Canvas, cx: int, y: int, lines: list[str], cs: CharSet, use_ascii: bool) -> None:
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

    _put_centered_lines(canvas, y + 4, cx, lines)


def _draw_control(canvas: Canvas, cx: int, y: int, lines: list[str], cs: CharSet, use_ascii: bool) -> None:
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

    _put_centered_lines(canvas, y + 4, cx, lines)


def _draw_entity(canvas: Canvas, cx: int, y: int, lines: list[str], cs: CharSet, use_ascii: bool) -> None:
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

    _put_centered_lines(canvas, y + 4, cx, lines)


def _draw_collections(canvas: Canvas, cx: int, y: int, width: int, h: int, lines: list[str], cs: CharSet, use_ascii: bool) -> None:
    """Draw a collections symbol: two overlapping rectangles."""
    style = "node"
    bx = cx - width // 2

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

    # Label centered in the front rectangle's interior
    _put_centered_lines(canvas, y + 2 + (h - 2 - len(lines)) // 2, cx, lines)


def _draw_participant_header(
    canvas: Canvas, cx: int, bw: int, header_height: int,
    participant, lines: list[str], cs: CharSet, use_ascii: bool,
) -> None:
    """Dispatch to the correct participant drawing function, bottom-aligned on the header."""
    kind = participant.kind
    h = _participant_height(participant, lines)
    y = _TOP_MARGIN + (header_height - h)

    if kind == "actor":
        _draw_actor(canvas, cx, y, lines, use_ascii)
    elif kind == "database":
        _draw_database(canvas, cx, y, bw, h, lines, cs)
    elif kind == "queue":
        _draw_queue(canvas, cx, y, bw, h, lines, cs, use_ascii)
    elif kind == "boundary":
        _draw_boundary(canvas, cx, y, lines, cs, use_ascii)
    elif kind == "control":
        _draw_control(canvas, cx, y, lines, cs, use_ascii)
    elif kind == "entity":
        _draw_entity(canvas, cx, y, lines, cs, use_ascii)
    elif kind == "collections":
        _draw_collections(canvas, cx, y, bw, h, lines, cs, use_ascii)
    else:
        bx = cx - bw // 2
        draw_rectangle(canvas, bx, y, bw, h, "\n".join(lines), cs, style="node")


def _compute_activation_ranges(flat_events: list[_FlatEvent], row_offsets: list[int]) -> dict[str, list[tuple[int, int]]]:
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


def render_sequence(
    diagram: SequenceDiagram,
    *,
    use_ascii: bool = False,
    padding_x: int = 4,
    gap: int = 16,
    max_label_width: int | None = None,
) -> Canvas:
    """Render a SequenceDiagram to a Canvas.

    With ``max_label_width`` every label (participants, messages, notes, frame
    titles) is wrapped to that many display cells; frame titles are wrapped to
    the frame width their contents dictate instead.
    """
    cs = ASCII if use_ascii else UNICODE

    # Flatten events for linear layout
    flat_events = _flatten_events(diagram.events)
    labels = _collect_labels(diagram, flat_events, max_label_width)

    col_centers, box_widths, width, height, header_height, row_offsets, block_bounds = _compute_layout(
        diagram, flat_events, labels, padding_x=padding_x, min_gap=gap,
        wrap_scope_labels=max_label_width is not None,
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
        _draw_participant_header(canvas, cx, bw, header_height, p, labels.participants[i], cs, use_ascii)

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
            left, right = block_bounds[id(ev.block)]
            block_border_stack.append((left, right, row))
        elif isinstance(ev, _BlockEnd):
            if block_border_stack:
                left, right, start_row = block_border_stack.pop()
                for r in range(start_row + 1, row):
                    canvas.put(r, left, cs.vertical, merge=False, style="node")
                    if right < canvas.width:
                        canvas.put(r, right, cs.vertical, merge=False, style="node")

    # ── 3. Draw events (messages, notes, blocks) ──────────────────
    for idx, ev in enumerate(flat_events):
        row = row_offsets[idx]
        lines = labels.events[idx]

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
            _draw_note(canvas, ev, lines, row, col_centers, diagram, cs, use_ascii)
            continue

        if isinstance(ev, _BlockStart):
            _draw_block_start(canvas, row, block_bounds[id(ev.block)], labels.block_titles[id(ev.block)], cs)
            continue

        if isinstance(ev, _BlockSectionBreak):
            _draw_block_section(
                canvas, row, block_bounds[id(ev.block)], labels.sections[id(ev.section)], cs, use_ascii,
            )
            continue

        if isinstance(ev, _BlockEnd):
            _draw_block_end(canvas, ev, row, block_bounds[id(ev.block)], cs, use_ascii)
            continue

        if isinstance(ev, Message):
            si = _participant_index(diagram, ev.source)
            ti = _participant_index(diagram, ev.target)
            if si < 0 or ti < 0:
                continue

            arrow_row = row + _extra_rows(lines)
            if si == ti:
                _draw_self_message(canvas, col_centers[si], arrow_row, ev, lines, cs, use_ascii)
            else:
                _draw_message(canvas, col_centers[si], col_centers[ti], arrow_row, ev, lines, cs, use_ascii)

    return canvas


# ── Block frame drawing ──────────────────────────────────────────

def _compute_block_bounds(
    diagram: SequenceDiagram,
    flat_events: list[_FlatEvent],
    col_centers: list[int],
    labels: _Labels,
    wrap_scope_labels: bool = False,
) -> dict[int, tuple[int, int]]:
    """Measure each frame bottom-up, including every branch and child frame.

    Records each frame's title and section lines in ``labels``. When wrapping,
    they are wrapped to the width the contents dictate so a title never widens
    its frame.
    """
    block_bounds: dict[int, tuple[int, int]] = {}
    content_stack: list[list[tuple[int, int]]] = []
    for event_index, event in enumerate(flat_events):
        if isinstance(event, _BlockStart):
            content_stack.append([])
            continue
        if isinstance(event, _BlockEnd):
            contents = content_stack.pop()
            content_left = min((left for left, _ in contents), default=col_centers[0])
            content_right = max((right for _, right in contents), default=content_left)
            frame_left = content_left - 2
            block = event.block
            prefix = f"[{block.kind}]"
            title = f"{prefix} {block.label}".rstrip()
            if wrap_scope_labels:
                # The title starts one cell inside the frame and is measured with
                # two cells of slack; sections start one cell further in.
                title_budget = max(content_right - content_left + 2, display_width(prefix) + 3)
                labels.block_titles[id(block)] = wrap_display_text(title, title_budget)
                for section in block.sections:
                    labels.sections[id(section)] = (
                        wrap_display_text(f"[{section.label}]", max(title_budget - 2, 3)) if section.label else []
                    )
            else:
                labels.block_titles[id(block)] = [title]
                for section in block.sections:
                    labels.sections[id(section)] = [f"[{section.label}]"] if section.label else []
            title_width = _lines_width(labels.block_titles[id(block)])
            section_width = max((
                _lines_width(labels.sections[id(section)]) + 2
                for section in block.sections if section.label
            ), default=0)
            frame_right = max(content_right + 2, frame_left + max(title_width, section_width) + 2)
            frame_bounds = (frame_left, frame_right)
            block_bounds[id(event.block)] = frame_bounds
            if content_stack:
                content_stack[-1].append(frame_bounds)
            continue
        if not content_stack:
            continue
        if isinstance(event, Message):
            source_index = _participant_index(diagram, event.source)
            target_index = _participant_index(diagram, event.target)
            if source_index < 0 or target_index < 0:
                continue
            message_left = min(col_centers[source_index], col_centers[target_index])
            lines = labels.events[event_index]
            message_right = max(col_centers[source_index], col_centers[target_index])
            if source_index == target_index:
                message_right = message_left + _self_loop_width(lines) - 1
            else:
                message_right = max(message_right, message_left + 1 + _lines_width(lines))
            content_stack[-1].append((message_left, message_right))
        elif isinstance(event, Note):
            note_bounds = _note_bounds(event, labels.events[event_index], col_centers, diagram)
            if note_bounds is not None:
                content_stack[-1].append(note_bounds)
        elif isinstance(event, (ActivateEvent, DestroyEvent)):
            participant_index = _participant_index(diagram, event.participant)
            if participant_index >= 0:
                participant_column = col_centers[participant_index]
                content_stack[-1].append((participant_column, participant_column))
    return block_bounds


def _clear_frame_row(canvas: Canvas, row: int, frame_bounds: tuple[int, int], cs: CharSet) -> None:
    """Blank a frame interior row so lifelines do not show through its text."""
    left, right = frame_bounds
    canvas.put(row, left, cs.vertical, merge=False, style="node")
    for c in range(left + 1, min(right, canvas.width)):
        canvas.blank(row, c)
    if right < canvas.width:
        canvas.put(row, right, cs.vertical, merge=False, style="node")


def _draw_block_start(
    canvas: Canvas,
    row: int,
    frame_bounds: tuple[int, int],
    title_lines: list[str],
    cs: CharSet,
) -> None:
    """Draw the top border of a block frame with its title lines below."""
    left, right = frame_bounds
    h_char = cs.horizontal
    style = "node"

    # Top border
    canvas.put(row, left, cs.top_left, merge=False, style=style)
    for c in range(left + 1, min(right, canvas.width)):
        canvas.put(row, c, h_char, merge=False, style=style)
    if right < canvas.width:
        canvas.put(row, right, cs.top_right, merge=False, style=style)

    for offset, line in enumerate(title_lines, start=1):
        if row + offset >= canvas.height:
            break
        _clear_frame_row(canvas, row + offset, frame_bounds, cs)
        canvas.put_text(row + offset, left + 1, line, style="edge_label")


def _draw_block_section(
    canvas: Canvas,
    row: int,
    frame_bounds: tuple[int, int],
    lines: list[str],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a dashed horizontal divider for else/and sections."""
    left, right = frame_bounds
    dash = "." if use_ascii else "┄"
    style = "node"

    canvas.put(row, left, cs.vertical, merge=False, style=style)
    for c in range(left + 1, min(right, canvas.width)):
        canvas.put(row, c, dash, merge=False, style=style)
    if right < canvas.width:
        canvas.put(row, right, cs.vertical, merge=False, style=style)

    # Section label after left border; extra lines continue below the divider
    for offset, line in enumerate(lines):
        if offset:
            _clear_frame_row(canvas, row + offset, frame_bounds, cs)
        canvas.put_text(row + offset, left + 2, line, style="edge_label", overwrite_spaces=True)


def _draw_block_end(
    canvas: Canvas,
    ev: _BlockEnd,
    row: int,
    frame_bounds: tuple[int, int],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw the bottom border of a block frame."""
    left, right = frame_bounds
    h_char = cs.horizontal
    style = "node"

    canvas.put(row, left, cs.bottom_left, merge=False, style=style)
    for c in range(left + 1, min(right, canvas.width)):
        canvas.put(row, c, h_char, merge=False, style=style)
    if right < canvas.width:
        canvas.put(row, right, cs.bottom_right, merge=False, style=style)


# ── Note drawing ─────────────────────────────────────────────────

def _note_bounds(
    note: Note, lines: list[str], col_centers: list[int], diagram: SequenceDiagram,
) -> tuple[int, int] | None:
    """Return inclusive note columns before canvas-edge clamping."""
    if not note.participants:
        return None
    note_width = _lines_width(lines) + 4
    # Determine horizontal placement
    if note.position == "rightof":
        pi = _participant_index(diagram, note.participants[0])
        if pi < 0:
            return None
        note_x = col_centers[pi] + 2
    elif note.position == "leftof":
        pi = _participant_index(diagram, note.participants[0])
        if pi < 0:
            return None
        note_x = col_centers[pi] - 2 - note_width
    elif note.position == "over":
        if len(note.participants) == 2:
            p1i = _participant_index(diagram, note.participants[0])
            p2i = _participant_index(diagram, note.participants[1])
            if p1i < 0 or p2i < 0:
                return None
            center = (col_centers[p1i] + col_centers[p2i]) // 2
            # Ensure spanning note covers both lifelines
            span_width = abs(col_centers[p1i] - col_centers[p2i]) + 4
            note_width = max(note_width, span_width)
        else:
            pi = _participant_index(diagram, note.participants[0])
            if pi < 0:
                return None
            center = col_centers[pi]
        note_x = center - note_width // 2
    else:
        return None

    return note_x, note_x + note_width - 1



def _draw_note(
    canvas: Canvas,
    note: Note,
    lines: list[str],
    row: int,
    col_centers: list[int],
    diagram: SequenceDiagram,
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a note box at the given row."""
    note_height = len(lines) + 2
    note_bounds = _note_bounds(note, lines, col_centers, diagram)
    if note_bounds is None:
        return
    raw_left, raw_right = note_bounds
    note_x = max(0, raw_left)
    note_width = raw_right - raw_left + 1

    # Clear the interior so lifeline chars don't bleed through
    for r in range(row, row + note_height):
        for c in range(note_x, note_x + note_width):
            if 0 <= r < canvas.height and 0 <= c < canvas.width:
                canvas._grid[r][c] = " "

    draw_rectangle(canvas, note_x, row, note_width, note_height, "\n".join(lines), cs, style="node")


# ── Message drawing ──────────────────────────────────────────────

def _put_label_above(canvas: Canvas, row: int, col: int, lines: list[str]) -> None:
    """Stack label lines so the last one sits directly above ``row``."""
    for offset, line in enumerate(lines):
        canvas.put_text(row - len(lines) + offset, col, line, style="edge_label", overwrite_spaces=True)


def _draw_message(
    canvas: Canvas,
    src_col: int,
    tgt_col: int,
    row: int,
    msg: Message,
    lines: list[str],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a horizontal message arrow on ``row`` with its label lines above it."""
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

    _put_label_above(canvas, row, left + 2, lines)


def _draw_self_message(
    canvas: Canvas,
    col: int,
    row: int,
    msg: Message,
    lines: list[str],
    cs: CharSet,
    use_ascii: bool,
) -> None:
    """Draw a self-referencing message (loop to the right) with its label above."""
    loop_width = _self_loop_width(lines)

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

    _put_label_above(canvas, row, col + 2, lines)
