"""Renderers draw with the CharSet they are given, not one they pick themselves."""
from dataclasses import replace

import pytest

from termaid.parser.blockdiagram import parse_block_diagram
from termaid.parser.classdiagram import parse_class_diagram
from termaid.parser.erdiagram import parse_er_diagram
from termaid.parser.flowchart import parse_flowchart
from termaid.parser.journey import parse_journey
from termaid.parser.sequence import parse_sequence_diagram
from termaid.renderer.blockdiagram import render_block_diagram
from termaid.renderer.charset import ASCII, UNICODE, default_charset
from termaid.renderer.classdiagram import render_class_diagram
from termaid.renderer.draw import render_graph_canvas
from termaid.renderer.erdiagram import render_er_diagram
from termaid.renderer.journey import render_journey
from termaid.renderer.sequence import render_sequence

# Distinctive glyphs that no built-in character set uses.
MARKED = replace(
    UNICODE,
    arrow_right="R", arrow_left="L", arrow_down="D", arrow_up="U",
    inherit_down="I", inherit_up="J", inherit_right="K", inherit_left="M",
    horizontal="=", line_horizontal="=",
)


def text(canvas) -> str:
    return canvas.to_string()


def test_default_charset():
    assert default_charset(False) is UNICODE
    assert default_charset(True) is ASCII


@pytest.mark.parametrize(
    "name, draw, expected",
    [
        ("flowchart", lambda cs: render_graph_canvas(parse_flowchart("graph LR\n  A --> B"), cs=cs), "R"),
        ("flowchart TD", lambda cs: render_graph_canvas(parse_flowchart("graph TD\n  A --> B"), cs=cs), "D"),
        ("sequence", lambda cs: render_sequence(parse_sequence_diagram("sequenceDiagram\n  A->>B: hi\n  B-->>A: yo"), cs=cs), "RL"),
        ("class dependency", lambda cs: render_class_diagram(parse_class_diagram("classDiagram\n  A --> B"), cs=cs), "D"),
        ("class inheritance", lambda cs: render_class_diagram(parse_class_diagram("classDiagram\n  A <|-- B"), cs=cs), "J"),
        ("journey", lambda cs: render_journey(parse_journey("journey\n  section S\n    a: 5: Me\n    b: 3: Me"), cs=cs), "R"),
        ("er", lambda cs: render_er_diagram(parse_er_diagram("erDiagram\n  A ||--o{ B : has"), cs=cs), "="),
        ("block", lambda cs: render_block_diagram(parse_block_diagram("block-beta\n  a b\n  a --> b"), cs=cs), "R"),
    ],
)
def test_renderer_uses_given_charset(name, draw, expected):
    output = text(draw(MARKED))
    for glyph in expected:
        assert glyph in output, (name, output)
    assert "►" not in output and "◄" not in output, (name, output)
