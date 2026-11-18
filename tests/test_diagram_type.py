"""What termaid does with a first line it cannot place (issue #51, M1 and L12)."""
from __future__ import annotations

import pytest

from termaid import UnknownDiagramError, parse, render
from termaid.claude_hook import StreamRenderer


@pytest.mark.parametrize("source,name", [
    ("sankey-beta\nA,B,10", "sankey"),
    ('C4Context\n  Person(a, "User")', "C4"),
    ("radar-beta\n  axis a, b", "radar"),
    ("zenuml\n  A.b()", "zenuml"),
    ("requirementDiagram\n  requirement r {\n  }", "requirement"),
])
def test_a_mermaid_type_termaid_does_not_draw_is_refused(source, name):
    with pytest.raises(UnknownDiagramError, match=f"does not draw {name} diagrams"):
        render(source)


@pytest.mark.parametrize("source", ["grpah LR\n  A --> B", "flowchrat TD\n  A --> B", "hello\nworld"])
def test_an_unknown_first_word_is_refused(source):
    with pytest.raises(UnknownDiagramError, match="Unknown diagram type"):
        render(source)
    with pytest.raises(UnknownDiagramError):
        parse(source)


def test_the_error_names_the_word_and_what_to_write():
    with pytest.raises(UnknownDiagramError) as error:
        render("grpah LR\n  A --> B")
    assert "'grpah'" in str(error.value) and "flowchart" in str(error.value)


def test_a_flowchart_with_no_header_keeps_its_first_line():
    out = render("A --> B\nB --> C")
    assert all(f"  {name}  " in out for name in "ABC")
    assert set(parse("A[Start] --> B").nodes) == {"A", "B"}


@pytest.mark.parametrize("header", [
    "graph LR", "flowchart TD", "graph", "flowchart-elk TD", "stateDiagram-v2", "stateDiagram",
])
def test_known_headers_still_draw(header):
    assert render(f"{header}\n  A --> B").strip()


def test_text_before_the_keyword_is_still_skipped():
    out = render('---\ntitle: x\n---\n%%{init: {"theme": "dark"}}%%\n%% a comment\ngraph LR\n  A --> B')
    assert "A" in out and "B" in out


def test_a_keyword_that_is_still_arriving_is_not_refused():
    assert render("sequ", partial=True) is not None
    with pytest.raises(UnknownDiagramError):
        render("sankey-beta\nA,B", partial=True)


def test_the_hook_shows_an_unknown_diagram_as_its_source():
    block = "```mermaid\nsankey-beta\nA,B,10\n```\n"
    assert StreamRenderer(width=80).feed(block, final=True) == block
