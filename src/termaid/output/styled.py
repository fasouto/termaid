"""Theme-independent styled output for editors and other non-terminal clients.

A ``StyledDocument`` carries the rendered diagram as lines of chunks. Each
chunk is a run of text sharing one style key. Joining the chunk texts of a
line gives exactly the matching line of ``termaid.render``. Colours are left
to the consumer, which maps style keys to its own palette.

Style keys:

- ``default``: background and anything not drawn with a role.
- ``node``, ``label``, ``bold_label``, ``italic_label``: node boxes and text.
- ``edge``, ``arrow``, ``edge_label``: connectors, arrow heads, edge text.
- ``subgraph``, ``subgraph_label``: subgraph borders and titles.
- ``section:N``, ``section:N:deep``: cells filled with the Nth section or
  series colour (gantt bars, kanban columns, quadrants, chart series).
  ``:deep`` is a lighter shade of the same colour, used for kanban cards.
- ``sectionfg:N``: text in the Nth section colour, without a fill.
- ``class:<name>``: a flowchart node using ``classDef <name>``
  (``class:default`` when the diagram defines a default class).
- ``nodestyle:<id>``: a flowchart node with its own ``style <id>`` line.
- ``class:<name>:text``, ``nodestyle:<id>:text``: the label of such a node,
  for its ``color:``. Without one, draw it as ``label``.
- ``linkstyle:<index>``: a flowchart edge covered by ``linkStyle``.

The ``class:``, ``nodestyle:`` and ``linkstyle:`` keys let a consumer apply
the diagram's own colours, so they are passed through rather than collapsed
to ``node`` or ``edge``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from ..renderer.canvas import Canvas


class StyledChunk(TypedDict):
    text: str
    style: str


class StyledDocument(TypedDict):
    version: int
    lines: list[list[StyledChunk]]


def serialize_canvas(canvas: Canvas | None) -> StyledDocument:
    """Group a canvas into styled chunks, trimmed the way ``Canvas.to_string`` trims."""
    lines: list[list[StyledChunk]] = []
    for row in canvas.to_styled_pairs() if canvas is not None else []:
        end = len(row)
        while end and not row[end - 1][0].strip():
            end -= 1
        chunks: list[StyledChunk] = []
        for ch, style in row[:end]:
            if not ch:
                continue
            style = style or "default"
            if chunks and chunks[-1]["style"] == style:
                chunks[-1]["text"] += ch
            else:
                chunks.append({"text": ch, "style": style})
        lines.append(chunks)
    while lines and not lines[-1]:
        lines.pop()
    return {"version": 1, "lines": lines}
