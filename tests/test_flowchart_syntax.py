"""Flowchart syntax fixed by pull requests #60 and #61 (issue #51, M4 to M12 and L11)."""
from __future__ import annotations

import pytest

from termaid import render
from termaid.graph.model import ArrowType, EdgeStyle
from termaid.graph.shapes import NodeShape
from termaid.parser.flowchart import parse_flowchart


def parse(body: str):
    return parse_flowchart("graph LR\n" + body)


def edges(body: str) -> list[tuple[str, str, str]]:
    return [(e.source, e.target, e.label) for e in parse(body).edges]


class TestIdsWithADash:
    @pytest.mark.parametrize("link", ["-->", "---", "-.->", "==>", "--o", "o--o", "<-->", "~~~"])
    def test_an_id_with_a_dash_is_one_node(self, link):
        graph = parse(f"go-on {link} B")
        assert set(graph.nodes) == {"go-on", "B"}
        assert [(e.source, e.target) for e in graph.edges] == [("go-on", "B")]

    def test_circle_and_cross_links_still_parse(self):
        graph = parse("A --o B\nB --x C\nC o--o D\nD x--x E")
        assert [(e.arrow_type_start, e.arrow_type_end) for e in graph.edges][2:] == [
            (ArrowType.CIRCLE, ArrowType.CIRCLE), (ArrowType.CROSS, ArrowType.CROSS),
        ]
        assert graph.edges[0].arrow_type_end == ArrowType.CIRCLE
        assert graph.edges[1].arrow_type_end == ArrowType.CROSS
        assert set(graph.nodes) == set("ABCDE")


class TestTextInsideALabel:
    @pytest.mark.parametrize("label", ["Load --> Parse", "x; y", "50%% done", "a:::b", "a -- b --> c", "f(x) --> g(y)"])
    def test_link_and_statement_syntax_inside_brackets_is_label_text(self, label):
        graph = parse(f"A[{label}] --> C")
        assert set(graph.nodes) == {"A", "C"}
        assert graph.nodes["A"].label == label
        assert edges(f"A[{label}] --> C") == [("A", "C", "")]

    def test_round_and_curly_labels_too(self):
        graph = parse("A(one --> two) --> B{three; four}")
        assert (graph.nodes["A"].label, graph.nodes["B"].label) == ("one --> two", "three; four")

    def test_a_semicolon_still_ends_a_statement_outside_a_label(self):
        assert edges("A[one] --> B[two]; B --> C") == [("A", "B", ""), ("B", "C", "")]

    def test_a_comment_after_a_statement_is_still_dropped(self):
        assert set(parse("A --> B %% the rest").nodes) == {"A", "B"}

    def test_an_arrow_after_an_unclosed_bracket_is_still_an_arrow(self):
        (edge,) = edges("A[open --> B")
        assert edge[1] == "B"


class TestEntityCodes:
    def test_a_code_in_an_edge_label_is_not_cut_at_its_semicolon(self):
        assert edges("A -->|#quot;hi#quot;| B") == [("A", "B", '"hi"')]

    def test_a_colour_in_a_style_statement_still_ends_at_its_semicolon(self):
        graph = parse("A --> B\nstyle A fill:#333;\nclassDef big fill:#f9f;")
        assert graph.class_defs["big"] == {"fill": "#f9f"}
        assert set(graph.nodes) == {"A", "B"}


class TestPipeLabels:
    @pytest.mark.parametrize("line,ends", [
        ("A --> |text| B", (ArrowType.ARROW, ArrowType.ARROW)),
        ("A --o|text| B", (ArrowType.ARROW, ArrowType.CIRCLE)),
        ("A --x|text| B", (ArrowType.ARROW, ArrowType.CROSS)),
        ("A o--o|text| B", (ArrowType.CIRCLE, ArrowType.CIRCLE)),
        ("A -->|text| B", (ArrowType.ARROW, ArrowType.ARROW)),
    ])
    def test_a_pipe_label_on_any_link(self, line, ends):
        graph = parse(line)
        assert edges(line) == [("A", "B", "text")]
        assert (graph.edges[0].arrow_type_start, graph.edges[0].arrow_type_end) == ends

    def test_a_node_called_x_or_o_is_still_a_node(self):
        assert edges("x -->|a| o") == [("x", "o", "a")]


class TestTextOnALink:
    @pytest.mark.parametrize("line,style", [
        ("A -- yes --> B", EdgeStyle.SOLID),
        ("A -- yes --- B", EdgeStyle.SOLID),
        ("A <-- yes --> B", EdgeStyle.SOLID),
        ("A -- yes --o B", EdgeStyle.SOLID),
        ("A -- yes ---> B", EdgeStyle.SOLID),
        ("A == yes ==> B", EdgeStyle.THICK),
        ("A == yes === B", EdgeStyle.THICK),
        ("A -. yes .-> B", EdgeStyle.DOTTED),
        ("A -. yes .- B", EdgeStyle.DOTTED),
    ])
    def test_text_between_the_two_halves_of_a_link(self, line, style):
        graph = parse(line)
        assert edges(line) == [("A", "B", "yes")]
        assert graph.edges[0].style == style

    def test_a_longer_closing_half_is_a_longer_link(self):
        assert parse("A -- yes ---> B").edges[0].min_length > parse("A -- yes --> B").edges[0].min_length

    def test_an_open_link_has_no_arrowhead_and_a_two_way_link_has_two(self):
        assert not parse("A -- yes --- B").edges[0].has_arrow_end
        both = parse("A <-- yes --> B").edges[0]
        assert both.has_arrow_start and both.has_arrow_end

    def test_text_and_pipe_labels_on_one_line(self):
        assert edges("A -- yes --> B -->|no| C") == [("A", "B", "yes"), ("B", "C", "no")]

    def test_a_long_run_of_link_characters_parses_quickly(self):
        from tests.test_hangs import finishes
        assert finishes(lambda: parse("A " + "o-- " * 4000 + "B"), seconds=10) is not None


class TestNodeData:
    def test_trapezoid_names_match_mermaid(self):
        graph = parse('A@{ shape: trap-b }\nB@{ shape: trap-t }\nC[/wide bottom\\]\nD[\\wide top/]')
        assert graph.nodes["A"].shape == graph.nodes["C"].shape == NodeShape.TRAPEZOID
        assert graph.nodes["B"].shape == graph.nodes["D"].shape == NodeShape.TRAPEZOID_ALT

    @pytest.mark.parametrize("name,shape", [
        ("decision", NodeShape.DIAMOND), ("database", NodeShape.CYLINDER), ("process", NodeShape.RECTANGLE),
        ("pill", NodeShape.STADIUM), ("subproc", NodeShape.SUBROUTINE), ("in-out", NodeShape.PARALLELOGRAM),
        ("manual", NodeShape.TRAPEZOID_ALT), ("odd", NodeShape.ASYMMETRIC), ("lean-right", NodeShape.PARALLELOGRAM),
    ])
    def test_shape_aliases(self, name, shape):
        assert parse(f"A@{{ shape: {name} }}").nodes["A"].shape == shape

    def test_data_on_an_id_with_a_dash(self):
        graph = parse("my-node@{ shape: circle } --> B")
        assert graph.nodes["my-node"].shape == NodeShape.CIRCLE
        assert set(graph.nodes) == {"my-node", "B"}

    def test_data_over_several_lines(self):
        graph = parse('A@{\n  shape: diamond\n  label: "Ready?"\n}\nA --> B')
        assert (graph.nodes["A"].shape, graph.nodes["A"].label) == (NodeShape.DIAMOND, "Ready?")
        assert set(graph.nodes) == {"A", "B"}

    def test_a_forgotten_closing_brace_does_not_swallow_the_diagram(self):
        assert [("B", "C", ""), ("C", "D", "")] == edges("A@{ shape: diamond\nB --> C\nC --> D")


class TestEdgeIds:
    def test_an_edge_id_is_not_part_of_a_node(self):
        graph = parse("A e1@--> B\ne1@{ animate: true }")
        assert set(graph.nodes) == {"A", "B"}
        assert edges("A e1@--> B") == [("A", "B", "")]

    def test_edge_ids_on_a_labelled_chain(self):
        assert edges("A e1@-->|x| B e2@--> C") == [("A", "B", "x"), ("B", "C", "")]

    def test_an_id_that_ends_in_an_at_sign_is_still_a_node(self):
        assert set(parse("user@ --> C").nodes) == {"user@", "C"}


class TestCommaListsAndAccessibility:
    def test_class_applies_to_every_node_in_a_list(self):
        graph = parse("A --> B\nclass A,B foo")
        assert graph.nodes["A"].style_class == graph.nodes["B"].style_class == "foo"

    def test_classdef_defines_every_name_in_a_list(self):
        graph = parse("A --> B\nclassDef a,,b fill:#f00")
        assert graph.class_defs == {"a": {"fill": "#f00"}, "b": {"fill": "#f00"}}

    def test_accessibility_lines_are_not_drawn(self):
        graph = parse("accTitle: My title\naccDescr: A description\naccDescr {\n  long text\n  more\n}\nA --> B")
        assert set(graph.nodes) == {"A", "B"}

    @pytest.mark.parametrize("link", ["-..-", "-...-"])
    def test_an_open_dotted_link_with_more_dots(self, link):
        graph = parse(f"A {link} B")
        assert edges(f"A {link} B") == [("A", "B", "")]
        assert graph.edges[0].style == EdgeStyle.DOTTED and not graph.edges[0].has_arrow_end


def test_one_line_with_all_of_it_draws():
    out = render(
        "graph LR\n  go-on -- yes --- B[Load --> Parse]\n  B -->|#quot;hi#quot;| C\n"
        "  C --> |spaced| D\n  D o--o|both| E\n"
    )
    for text in ("go-on", "yes", "Load --> Parse", '"hi"', "spaced", "both"):
        assert text in out


class TestCircleAndCrossEnds:
    @pytest.mark.parametrize("link, style, start, end", [
        ("==x", EdgeStyle.THICK, None, ArrowType.CROSS),
        ("==o", EdgeStyle.THICK, None, ArrowType.CIRCLE),
        ("-.-x", EdgeStyle.DOTTED, None, ArrowType.CROSS),
        ("-.-o", EdgeStyle.DOTTED, None, ArrowType.CIRCLE),
        ("o==o", EdgeStyle.THICK, ArrowType.CIRCLE, ArrowType.CIRCLE),
        ("x-.-x", EdgeStyle.DOTTED, ArrowType.CROSS, ArrowType.CROSS),
        ("---x", EdgeStyle.SOLID, None, ArrowType.CROSS),
    ])
    def test_thick_and_dotted_links_take_circle_and_cross_ends(self, link, style, start, end):
        graph = parse(f"A {link} B")
        assert set(graph.nodes) == {"A", "B"}
        (edge,) = graph.edges
        assert edge.style == style
        assert edge.has_arrow_end and edge.arrow_type_end == end
        assert edge.has_arrow_start == (start is not None)
        if start is not None:
            assert edge.arrow_type_start == start

    @pytest.mark.parametrize("line, end", [
        ("A --oB", ArrowType.CIRCLE),
        ("C --xD", ArrowType.CROSS),
        ("E---oF", ArrowType.CIRCLE),
        ("G--oH", ArrowType.CIRCLE),
    ])
    def test_an_end_mark_needs_no_space_before_the_node(self, line, end):
        # Mermaid's docs: "A---oB" draws a circle edge from A to B.
        graph = parse(line)
        (edge,) = graph.edges
        assert len(graph.nodes) == 2
        assert edge.arrow_type_end == end

    def test_a_longer_cross_link_is_longer(self):
        assert parse("A ---x B").edges[0].min_length == parse("A ---> B").edges[0].min_length == 2


class TestMarkdownStrings:
    def test_underscores_mark_italic_and_bold(self):
        graph = parse('A["`This **is** _Markdown_ and __bold__`"]')
        node = graph.nodes["A"]
        assert node.label == "This is Markdown and bold"
        styled = {(s.text, s.bold, s.italic) for s in node.label_segments}
        assert {("Markdown", False, True), ("bold", True, False)} <= styled

    def test_an_underscore_inside_a_word_is_text(self):
        assert parse('A["`snake_case_name`"]').nodes["A"].label == "snake_case_name"

    @pytest.mark.parametrize("line", ['A -->|"`**yes**`"| B', 'A -- "`**yes**` " --> B'])
    def test_an_edge_label_drops_the_markdown_marks(self, line):
        assert edges(line) == [("A", "B", "yes")]

    def test_a_subgraph_title_drops_the_markdown_marks(self):
        graph = parse('subgraph s1 ["`**Bold** title`"]\n  a --> b\nend')
        assert graph.subgraphs[0].label == "Bold title"

    def test_drawn_without_the_marks(self):
        out = render('graph LR\n  A["`This **is** _Markdown_`"] -->|"`**yes**`"| B')
        assert "This is Markdown" in out
        assert "yes" in out
        assert not set("`*_") & set(out)
