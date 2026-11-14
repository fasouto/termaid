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
    if canvas is None:
        return {"version": 1, "lines": []}

    from ..renderer.canvas import Canvas

    # Read built-in cells directly; honor custom pair conversion.
    if type(canvas) is Canvas and "to_styled_pairs" not in vars(canvas):
        rows = ((canvas.width, (canvas._grid[r], canvas._style_grid[r]))
                for r in range(canvas.height))

        def pair_at(row, column):
            return row[0][column], row[1][column]
    else:
        rows = ((len(row), row) for row in canvas.to_styled_pairs())

        def pair_at(row, column):
            return row[column]

    text_cache: dict[str, str] = {}
    lines: list[list[StyledChunk]] = []
    chunks: list[StyledChunk] = []
    for end, row in rows:
        while end and not pair_at(row, end - 1)[0].strip():
            end -= 1
        chunks.clear()
        for column in range(end):
            ch, style = pair_at(row, column)
            if not ch:
                continue
            style = style or "default"
            if chunks and chunks[-1]["style"] == style:
                text = chunks[-1]["text"] + ch
                chunks[-1]["text"] = (
                    text_cache.get(text, text) if type(text) is str else text
                )
            else:
                chunks.append({"text": ch, "style": style})
        for chunk in chunks:
            text = chunk["text"]
            if type(text) is str:
                chunk["text"] = text_cache.setdefault(text, text)
        lines.append(chunks.copy())
    while lines and not lines[-1]:
        lines.pop()
    return {"version": 1, "lines": lines}
