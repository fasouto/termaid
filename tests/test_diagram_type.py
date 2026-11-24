"""What termaid does with a first line it cannot place (issue #51, M1 and L12)."""
from __future__ import annotations

import pytest

from termaid import parse, render, type_problem
from termaid.cli import main
from termaid.claude_hook import StreamRenderer


@pytest.mark.parametrize("source,name", [
    ("sankey-beta\nA,B,10", "sankey"),
    ('C4Context\n  Person(a, "User")', "C4"),
    ("radar-beta\n  axis a, b", "radar"),
    ("zenuml\n  A.b()", "zenuml"),
    ("requirementDiagram\n  requirement r {\n  }", "requirement"),
])
def test_a_mermaid_type_termaid_does_not_draw_draws_nothing(source, name):
    assert render(source) == ""
    assert type_problem(source) == f"termaid does not draw {name} diagrams."


@pytest.mark.parametrize("source", ["grpah LR\n  A --> B", "flowchrat TD\n  A --> B", "hello\nworld"])
def test_an_unknown_first_word_draws_nothing(source):
    assert render(source) == ""
    assert not parse(source).nodes
    assert "Unknown diagram type" in type_problem(source)


def test_the_problem_names_the_word_and_what_to_write():
    problem = type_problem("grpah LR\n  A --> B")
    assert "'grpah'" in problem and "flowchart TD" in problem
    assert type_problem("graph LR\n  A --> B") is None and type_problem("A --> B") is None


def test_the_command_line_says_why_nothing_was_drawn(tmp_path, capsys):
    path = tmp_path / "typo.mmd"
    path.write_text("grpah LR\n  A --> B\n", encoding="utf-8")
    assert main([str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("Error: Unknown diagram type 'grpah'.")
    path.write_text("sankey-beta\nA,B,10\n", encoding="utf-8")
    assert main([str(path)]) == 1
    assert capsys.readouterr().err == "Error: termaid does not draw sankey diagrams.\n"


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


def test_a_keyword_that_is_still_arriving_is_given_to_the_flowchart_parser_as_before():
    assert render("sequ", partial=True) == ""
    assert render("sankey-beta\nA,B", partial=True) == ""


def test_the_hook_shows_an_unknown_diagram_as_its_source():
    block = "```mermaid\nsankey-beta\nA,B,10\n```\n"
    assert StreamRenderer(width=80).feed(block, final=True) == block


@pytest.mark.parametrize("source", [
    "graphql --> api", "pieces --> board", "timelineStart --> done", "kanbanCol --> next",
    "mindmapping --> notes", "blocker --> fix", "packets --> wire", "flowcharts --> docs",
])
def test_a_headerless_flowchart_whose_first_id_starts_with_a_keyword(source):
    first, second = source.split(" --> ")
    assert type_problem(source) is None
    assert set(parse(source).nodes) == {first, second}
    out = render(source)
    assert f" {first} " in out and f" {second} " in out and "▼" in out


@pytest.mark.parametrize("header", [
    "stateDiagram-v2", "xychart-beta", "block-beta", "packet-beta", "architecture-beta", "flowchart-elk TD",
    "gitGraph", "gitGraph:", "gitGraph LR:", "pie title Pets", "pie showData", "sequenceDiagram", "quadrantChart",
])
def test_a_keyword_with_a_suffix_is_still_its_type(header):
    assert type_problem(header + "\n") is None


def test_render_rich_draws_nothing_for_a_type_it_cannot_draw():
    pytest.importorskip("rich")
    from termaid import render_rich
    for source in ("sankey-beta\nA,B,10", "grpah LR\n  A --> B"):
        assert render_rich(source).plain == ""


def test_the_command_line_says_why_with_a_theme_too(tmp_path, capsys):
    pytest.importorskip("rich")
    path = tmp_path / "s.mmd"
    path.write_text("sankey-beta\nA,B,10\n", encoding="utf-8")
    assert main([str(path), "--theme", "neon"]) == 1
    assert capsys.readouterr().err == "Error: termaid does not draw sankey diagrams.\n"
