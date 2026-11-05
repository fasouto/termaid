"""Shape renderers for node drawing.

Each shape renderer knows how to draw a node in a specific shape
onto the canvas, and how to compute attachment points for edges.
"""
from __future__ import annotations

from typing import Protocol

from ..canvas import Canvas
from ...utils import display_width
from ..charset import CharSet
from ...graph.shapes import NodeShape


class ShapeRenderer(Protocol):
    """Protocol for shape renderers."""

    def draw(
        self,
        canvas: Canvas,
        x: int,
        y: int,
        width: int,
        height: int,
        label: str,
        cs: CharSet,
    ) -> None:
        """Draw the shape on the canvas."""
        ...


def draw_rectangle(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a rectangular box with label centered."""
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

    # Label (centered)
    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_rounded(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a rounded box."""
    canvas.put(y, x, cs.round_top_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, cs.round_top_right, style=style)

    canvas.put(y + height - 1, x, cs.round_bottom_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, cs.round_bottom_right, style=style)

    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_stadium(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a stadium (pill) shape.

    With room for straight sides beside the label, it is a capsule whose corners
    step in::

         ╭──────────╮
        ╭╯          ╰╮
        │    Done    │
        ╰╮          ╭╯
         ╰──────────╯

    Shorter, it is a rounded box with round ends for sides::

        ╭──────────╮
        ❨   Done   ❩
        ╰──────────╯

    ASCII draws the capsule with diagonal steps (``/  \\``) and the short form with
    ``( )`` sides.
    """
    left, right = x, x + width - 1
    bottom = y + height - 1
    lines = label.split("\n") if "\n" in label else label.split("\\n")
    # The capsule's stepped rows must stay clear of the label and of the middle row,
    # where edges attach, so it needs two straight rows more than the label.
    if width < 5 or not (height >= 5 and height - 4 >= len(lines)):
        canvas.put(y, left, cs.round_top_left, style=style)
        canvas.put(bottom, left, cs.round_bottom_left, style=style)
        for c in range(left + 1, right):
            canvas.put(y, c, cs.horizontal, style=style)
            canvas.put(bottom, c, cs.horizontal, style=style)
        canvas.put(y, right, cs.round_top_right, style=style)
        canvas.put(bottom, right, cs.round_bottom_right, style=style)
        for r in range(y + 1, bottom):
            canvas.put(r, left, cs.stadium_left, style=style)
            canvas.put(r, right, cs.stadium_right, style=style)
        _draw_label(canvas, x, y, width, height, label, style=style)
        return

    # Capsule: top and bottom edges inset by one column at each end...
    canvas.put(y, left + 1, cs.round_top_left, style=style)
    canvas.put(bottom, left + 1, cs.round_bottom_left, style=style)
    for c in range(left + 2, right - 1):
        canvas.put(y, c, cs.horizontal, style=style)
        canvas.put(bottom, c, cs.horizontal, style=style)
    canvas.put(y, right - 1, cs.round_top_right, style=style)
    canvas.put(bottom, right - 1, cs.round_bottom_right, style=style)
    # ...stepping out on the first and last body rows, with straight sides between.
    if cs.round_top_left == "+":  # ASCII: diagonal steps
        canvas.put(y + 1, left, "/", style=style)
        canvas.put(y + 1, right, "\\", style=style)
        canvas.put(bottom - 1, left, "\\", style=style)
        canvas.put(bottom - 1, right, "/", style=style)
    else:
        canvas.put(y + 1, left, cs.round_top_left, style=style)
        canvas.put(y + 1, left + 1, cs.round_bottom_right, style=style)
        canvas.put(y + 1, right - 1, cs.round_bottom_left, style=style)
        canvas.put(y + 1, right, cs.round_top_right, style=style)
        canvas.put(bottom - 1, left, cs.round_bottom_left, style=style)
        canvas.put(bottom - 1, left + 1, cs.round_top_right, style=style)
        canvas.put(bottom - 1, right - 1, cs.round_top_left, style=style)
        canvas.put(bottom - 1, right, cs.round_bottom_right, style=style)
    for r in range(y + 2, bottom - 1):
        canvas.put(r, left, cs.vertical, style=style)
        canvas.put(r, right, cs.vertical, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_subroutine(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a subroutine (double-bordered) box."""
    draw_rectangle(canvas, x, y, width, height, label, cs, style=style)
    # Inner vertical lines
    if width > 4:
        for r in range(y + 1, y + height - 1):
            canvas.put(r, x + 1, cs.vertical, style=style)
            canvas.put(r, x + width - 2, cs.vertical, style=style)


def draw_diamond(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a diamond (decision) with ◆ markers at top/bottom center.

        ┌────◆────┐
        │         │
        │ decide? │
        │         │
        └────◆────┘
    """
    cx = x + width // 2
    is_unicode = cs.horizontal == "─"
    marker = "◇" if is_unicode else "*"

    # Top border with ◆ at center
    canvas.put(y, x, cs.top_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, cs.top_right, style=style)
    canvas.put(y, cx, marker, merge=False, style=style)

    # Bottom border with ◆ at center
    canvas.put(y + height - 1, x, cs.bottom_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, cs.bottom_right, style=style)
    canvas.put(y + height - 1, cx, marker, merge=False, style=style)

    # Side borders
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_hexagon(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a hexagon shape."""
    # Use a simplified box with angled sides
    # Top border
    canvas.put(y, x + 1, "/", style=style)
    for c in range(x + 2, x + width - 2):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 2, "\\", style=style)

    # Bottom border
    canvas.put(y + height - 1, x + 1, "\\", style=style)
    for c in range(x + 2, x + width - 2):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 2, "/", style=style)

    # Side borders
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical if cs.horizontal == "─" else "|", style=style)
        canvas.put(r, x + width - 1, cs.vertical if cs.horizontal == "─" else "|", style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_circle(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a circle with ◯ markers at top/bottom center.

        ╭────◯────╮
        │         │
        │  text   │
        │         │
        ╰────◯────╯
    """
    cx = x + width // 2
    is_unicode = cs.horizontal == "─"
    marker = "◯" if is_unicode else "O"

    # Draw as rounded box first
    draw_rounded(canvas, x, y, width, height, label, cs, style=style)

    # Place ◯ markers at top/bottom center (overwrite the ─ there)
    canvas.put(y, cx, marker, merge=False, style=style)
    canvas.put(y + height - 1, cx, marker, merge=False, style=style)


def draw_double_circle(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a double circle shape."""
    draw_rounded(canvas, x, y, width, height, label, cs, style=style)
    # Inner border if space allows
    if width > 4 and height > 2:
        canvas.put(y + 1, x + 1, cs.round_top_left, style=style)
        for c in range(x + 2, x + width - 2):
            canvas.put(y + 1, c, cs.horizontal, style=style)
        canvas.put(y + 1, x + width - 2, cs.round_top_right, style=style)

        canvas.put(y + height - 2, x + 1, cs.round_bottom_left, style=style)
        for c in range(x + 2, x + width - 2):
            canvas.put(y + height - 2, c, cs.horizontal, style=style)
        canvas.put(y + height - 2, x + width - 2, cs.round_bottom_right, style=style)


def draw_asymmetric(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw an asymmetric (flag) shape: >text]."""
    # Left side is a point
    cy = y + height // 2
    for r in range(y, y + height):
        if r < cy:
            canvas.put(r, x, "\\", style=style)
        elif r == cy:
            canvas.put(r, x, ">", style=style)
        else:
            canvas.put(r, x, "/", style=style)

    # Right side is straight
    canvas.put(y, x + width - 1, cs.top_right, style=style)
    canvas.put(y + height - 1, x + width - 1, cs.bottom_right, style=style)
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    # Top and bottom borders
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
        canvas.put(y + height - 1, c, cs.horizontal, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_cylinder(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a cylinder (database) shape."""
    # Top ellipse
    canvas.put(y, x, cs.round_top_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, cs.round_top_right, style=style)

    # Second row: the lid's front rim, inside the body's sides
    canvas.put(y + 1, x + 1, cs.lid_left, style=style)
    for c in range(x + 2, x + width - 2):
        canvas.put(y + 1, c, cs.lid_fill, style=style)
    canvas.put(y + 1, x + width - 2, cs.lid_right, style=style)

    # Body
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    # Bottom ellipse
    canvas.put(y + height - 1, x, cs.round_bottom_left, style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, cs.round_bottom_right, style=style)

    # Centre the label in the body, below the lid row, so the lid never draws over it.
    # (Layout reserves the lid row: see compute_sizes.)
    _draw_label(canvas, x, y + 1, width, height - 1, label, style=style)


def draw_trapezoid(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a trapezoid: /text\\ — top corners slant inward."""
    # Top: /───\
    canvas.put(y, x, "/", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, "\\", style=style)

    # Bottom: \───/
    canvas.put(y + height - 1, x, "\\", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, "/", style=style)

    # Straight sides
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_trapezoid_alt(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw inverted trapezoid: \\text/ — bottom corners slant inward."""
    # Top: \───/
    canvas.put(y, x, "\\", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, "/", style=style)

    # Bottom: /───\
    canvas.put(y + height - 1, x, "/", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, "\\", style=style)

    # Straight sides
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_parallelogram(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw parallelogram leaning right: /text/ — all corners use /."""
    # Top: /───/
    canvas.put(y, x, "/", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, "/", style=style)

    # Bottom: /───/
    canvas.put(y + height - 1, x, "/", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, "/", style=style)

    # Straight sides
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def draw_parallelogram_alt(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw parallelogram leaning left: \\text\\ — all corners use \\."""
    # Top: \───\
    canvas.put(y, x, "\\", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y, c, cs.horizontal, style=style)
    canvas.put(y, x + width - 1, "\\", style=style)

    # Bottom: \───\
    canvas.put(y + height - 1, x, "\\", style=style)
    for c in range(x + 1, x + width - 1):
        canvas.put(y + height - 1, c, cs.horizontal, style=style)
    canvas.put(y + height - 1, x + width - 1, "\\", style=style)

    # Straight sides
    for r in range(y + 1, y + height - 1):
        canvas.put(r, x, cs.vertical, style=style)
        canvas.put(r, x + width - 1, cs.vertical, style=style)

    _draw_label(canvas, x, y, width, height, label, style=style)


def _draw_label(
    canvas: Canvas, x: int, y: int, width: int, height: int, label: str,
    style: str = "",
) -> None:
    """Draw centered label text inside a shape."""
    if style.startswith(("class:", "nodestyle:")):
        label_style = f"{style}:text"  # lets classDef color: tint the label
    else:
        label_style = "label" if style else ""
    # Split on real newlines (from notes) or literal \n (from flowchart wrapping)
    if "\n" in label:
        lines = label.split("\n")
    elif "\\n" in label:
        lines = label.split("\\n")
    else:
        lines = [label]
    start_row = y + (height - len(lines)) // 2
    for i, line in enumerate(lines):
        row = start_row + i
        col = x + (width - display_width(line)) // 2
        if 0 <= row < canvas.height:
            canvas.put_text(row, col, line, style=label_style)


def draw_start_state(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a start state: filled circle (●)."""
    cy = y + height // 2
    cx = x + width // 2
    canvas.put(cy, cx, "●" if cs.horizontal == "─" else "*", style=style)


def draw_end_state(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw an end state: bullseye (◉)."""
    cy = y + height // 2
    cx = x + width // 2
    canvas.put(cy, cx, "◉" if cs.horizontal == "─" else "@", style=style)


def draw_fork_join(
    canvas: Canvas, x: int, y: int, width: int, height: int,
    label: str, cs: CharSet, style: str = "",
) -> None:
    """Draw a fork/join bar: solid thick block."""
    bar_char = "━" if cs.horizontal == "─" else "="
    for r in range(y, y + height):
        for c in range(x, x + width):
            canvas.put(r, c, bar_char, style=style)


# Shape renderer registry
SHAPE_RENDERERS = {
    NodeShape.RECTANGLE: draw_rectangle,
    NodeShape.ROUNDED: draw_rounded,
    NodeShape.STADIUM: draw_stadium,
    NodeShape.SUBROUTINE: draw_subroutine,
    NodeShape.DIAMOND: draw_diamond,
    NodeShape.HEXAGON: draw_hexagon,
    NodeShape.CIRCLE: draw_circle,
    NodeShape.DOUBLE_CIRCLE: draw_double_circle,
    NodeShape.ASYMMETRIC: draw_asymmetric,
    NodeShape.CYLINDER: draw_cylinder,
    NodeShape.PARALLELOGRAM: draw_parallelogram,
    NodeShape.PARALLELOGRAM_ALT: draw_parallelogram_alt,
    NodeShape.TRAPEZOID: draw_trapezoid,
    NodeShape.TRAPEZOID_ALT: draw_trapezoid_alt,
    NodeShape.START_STATE: draw_start_state,
    NodeShape.END_STATE: draw_end_state,
    NodeShape.FORK_JOIN: draw_fork_join,
    NodeShape.JUNCTION: lambda canvas, x, y, width, height, label, cs, style="": None,
}
