"""Room beside a state for the notes on it."""
from __future__ import annotations

from ..graph.model import Graph, GraphNote
from ..utils import display_width
from .grid import GridLayout

# Columns between a note and the box beside it
NOTE_GAP = 2


def note_size(note: GraphNote) -> tuple[int, int]:
    """Width and height of a note's box."""
    lines = note.text.split("\n")
    return max(display_width(line) for line in lines) + 4, len(lines) + 2


def note_on_right(graph: Graph, note: GraphNote) -> bool:
    """Whether the note goes right of its box in the layout.

    RL is laid out as LR and turned around after, so there a note's side
    is swapped here to land on the side it names.
    """
    flipped = graph.direction.is_reversed and not graph.direction.is_vertical
    return (note.position == "rightof") != flipped


def reserve_note_room(graph: Graph, layout: GridLayout) -> None:
    """Widen the gap column beside each note's box so the note fits there.

    The leftmost column has no gap to its left, so a left note on one of
    its boxes moves the whole layout right instead.
    """
    for note in graph.notes:
        p = layout.placements.get(note.target)
        if p is None:
            continue
        need = note_size(note)[0] + 2 * NOTE_GAP
        col = p.grid.col + (2 if note_on_right(graph, note) else -2)
        if col >= 0:
            layout.col_widths[col] = max(layout.col_widths.get(col, 1), need)
        else:
            layout.offset_x = max(layout.offset_x, need)
