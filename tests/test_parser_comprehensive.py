"""Comprehensive parser tests modeled after beautiful-mermaid's parser.test.ts.

Covers: all edge types with arrow direction, edge styles, labels,
chained arrows, subgraphs, ampersand operator, class definitions,
and edge cases.
"""
from __future__ import annotations

import pytest

from termaid import render
from termaid.parser.flowchart import parse_flowchart
from termaid.graph.model import Direction, Edge, EdgeStyle
from termaid.graph.shapes import NodeShape


# ── Bidirectional arrows ──────────────────────────────────────────────────────

class TestBidirectionalArrows:
    """Test all bidirectional arrow syntax variants."""

    def test_solid_bidir(self):
        g = parse_flowchart("graph LR\n  A <--> B")
        assert g.edges[0].has_arrow_start is True
        assert g.edges[0].has_arrow_end is True
        assert g.edges[0].style == EdgeStyle.SOLID

    def test_dotted_bidir(self):
        g = parse_flowchart("graph LR\n  A <-.-> B")
        assert g.edges[0].has_arrow_start is True
        assert g.edges[0].has_arrow_end is True
        assert g.edges[0].style == EdgeStyle.DOTTED

    def test_thick_bidir(self):
        g = parse_flowchart("graph LR\n  A <==> B")
        assert g.edges[0].has_arrow_start is True
        assert g.edges[0].has_arrow_end is True
        assert g.edges[0].style == EdgeStyle.THICK

    def test_bidir_with_label(self):
        g = parse_flowchart("graph LR\n  A <-->|text| B")
        assert g.edges[0].has_arrow_start is True
        assert g.edges[0].has_arrow_end is True
        assert g.edges[0].label == "text"

    def test_long_bidir(self):
        g = parse_flowchart("graph LR\n  A <----> B")
        assert g.edges[0].has_arrow_start is True
        assert g.edges[0].has_arrow_end is True


# ── No-arrow edges ────────────────────────────────────────────────────────────

class TestNoArrowEdges:
    """Test edges without arrow heads."""

    def test_solid_open(self):
        g = parse_flowchart("graph LR\n  A --- B")
        assert g.edges[0].has_arrow_start is False
        assert g.edges[0].has_arrow_end is False
        assert g.edges[0].style == EdgeStyle.SOLID

    def test_dotted_open(self):
        g = parse_flowchart("graph LR\n  A -.- B")
        assert g.edges[0].has_arrow_start is False
        assert g.edges[0].has_arrow_end is False
        assert g.edges[0].style == EdgeStyle.DOTTED

    def test_thick_open(self):
        g = parse_flowchart("graph LR\n  A === B")
        assert g.edges[0].has_arrow_start is False
        assert g.edges[0].has_arrow_end is False
        assert g.edges[0].style == EdgeStyle.THICK

    def test_invisible(self):
        g = parse_flowchart("graph LR\n  A ~~~ B")
        assert g.edges[0].style == EdgeStyle.INVISIBLE
        assert g.edges[0].has_arrow_start is False
        assert g.edges[0].has_arrow_end is False


# ── Unidirectional arrows ────────────────────────────────────────────────────

class TestUnidirectionalArrows:
    """Test standard forward-only arrows."""

    def test_solid_arrow(self):
        g = parse_flowchart("graph LR\n  A --> B")
        assert g.edges[0].has_arrow_start is False
        assert g.edges[0].has_arrow_end is True
        assert g.edges[0].style == EdgeStyle.SOLID

    def test_dotted_arrow(self):
        g = parse_flowchart("graph LR\n  A -.-> B")
        assert g.edges[0].has_arrow_start is False
        assert g.edges[0].has_arrow_end is True
        assert g.edges[0].style == EdgeStyle.DOTTED

    def test_thick_arrow(self):
        g = parse_flowchart("graph LR\n  A ==> B")
        assert g.edges[0].has_arrow_start is False
        assert g.edges[0].has_arrow_end is True
        assert g.edges[0].style == EdgeStyle.THICK


# ── Edge labels ───────────────────────────────────────────────────────────────

class TestEdgeLabels:
    """Test all label syntax variants."""

    def test_pipe_label(self):
        g = parse_flowchart("graph LR\n  A -->|text| B")
        assert g.edges[0].label == "text"

    def test_inline_solid_label(self):
        g = parse_flowchart("graph LR\n  A -- text --> B")
        assert g.edges[0].label == "text"
        assert g.edges[0].style == EdgeStyle.SOLID

    def test_inline_thick_label(self):
        g = parse_flowchart("graph LR\n  A == text ==> B")
        assert g.edges[0].label == "text"
        assert g.edges[0].style == EdgeStyle.THICK

    def test_inline_dotted_label(self):
        g = parse_flowchart("graph LR\n  A -. text .-> B")
        assert g.edges[0].label == "text"
        assert g.edges[0].style == EdgeStyle.DOTTED

    def test_multi_word_label(self):
        g = parse_flowchart("graph LR\n  A -->|hello world| B")
        assert g.edges[0].label == "hello world"


# ── Chained arrows ────────────────────────────────────────────────────────────

class TestChainedArrows:
    """Test chained arrow syntax: A --> B --> C."""

    def test_simple_chain(self):
        g = parse_flowchart("graph LR\n  A --> B --> C")
        assert len(g.edges) == 2
        assert g.edges[0].source == "A"
        assert g.edges[0].target == "B"
        assert g.edges[1].source == "B"
        assert g.edges[1].target == "C"

    def test_long_chain(self):
        g = parse_flowchart("graph LR\n  A --> B --> C --> D --> E")
        assert len(g.edges) == 4

    def test_chain_with_labels(self):
        g = parse_flowchart("graph LR\n  A -- x --> B -- y --> C")
        assert g.edges[0].label == "x"
        assert g.edges[1].label == "y"

    def test_chain_mixed_styles(self):
        g = parse_flowchart("graph LR\n  A --> B -.-> C ==> D")
        assert g.edges[0].style == EdgeStyle.SOLID
        assert g.edges[1].style == EdgeStyle.DOTTED
        assert g.edges[2].style == EdgeStyle.THICK


# ── Ampersand operator ────────────────────────────────────────────────────────

class TestAmpersandOperator:
    """Test the & operator for parallel connections."""

    def test_rhs_ampersand(self):
        g = parse_flowchart("graph LR\n  A --> B & C")
        assert len(g.edges) == 2
        targets = {e.target for e in g.edges}
        assert targets == {"B", "C"}

    def test_lhs_ampersand(self):
        g = parse_flowchart("graph LR\n  A & B --> C")
        assert len(g.edges) == 2
        sources = {e.source for e in g.edges}
        assert sources == {"A", "B"}

    def test_both_ampersand(self):
        g = parse_flowchart("graph LR\n  A & B --> C & D")
        assert len(g.edges) == 4

    def test_three_way_ampersand(self):
        g = parse_flowchart("graph LR\n  A --> B & C & D")
        assert len(g.edges) == 3


# ── Subgraphs ────────────────────────────────────────────────────────────────

class TestSubgraphs:
    """Test subgraph parsing."""

    def test_basic_subgraph(self):
        g = parse_flowchart("graph LR\n  subgraph one\n    A --> B\n  end")
        assert len(g.subgraphs) == 1
        assert g.subgraphs[0].id == "one"

    def test_subgraph_with_label(self):
        g = parse_flowchart(
            "graph LR\n  subgraph ide1 [My Label]\n    A\n  end"
        )
        assert g.subgraphs[0].label == "My Label"

    def test_subgraph_contains_nodes(self):
        g = parse_flowchart("graph LR\n  subgraph s1\n    A --> B\n  end")
        assert "A" in g.subgraphs[0].node_ids
        assert "B" in g.subgraphs[0].node_ids

    def test_nested_subgraphs(self):
        g = parse_flowchart(
            "graph LR\n"
            "  subgraph outer\n"
            "    subgraph inner\n"
            "      A\n"
            "    end\n"
            "  end"
        )
        assert len(g.subgraphs) == 1
        assert len(g.subgraphs[0].children) == 1
        assert g.subgraphs[0].children[0].id == "inner"

    def test_subgraph_direction_override(self):
        g = parse_flowchart(
            "graph LR\n"
            "  subgraph s1\n"
            "    direction TB\n"
            "    A --> B\n"
            "  end"
        )
        assert g.subgraphs[0].direction == Direction.TB

    def test_multiple_subgraphs(self):
        g = parse_flowchart(
            "graph LR\n"
            "  subgraph s1\n"
            "    A\n"
            "  end\n"
            "  subgraph s2\n"
            "    B\n"
            "  end"
        )
        assert len(g.subgraphs) == 2


# ── Class definitions ─────────────────────────────────────────────────────────

class TestClassDef:
    """Test classDef and class assignments."""

    def test_classdef(self):
        g = parse_flowchart(
            "graph LR\n  A --> B\n  classDef red fill:#f00,stroke:#333"
        )
        assert "red" in g.class_defs

    def test_class_shorthand(self):
        g = parse_flowchart("graph LR\n  A:::myClass --> B")
        assert g.nodes["A"].style_class == "myClass"


# ── Edge properties ───────────────────────────────────────────────────────────

class TestEdgeProperties:
    """Test Edge model properties."""

    def test_is_bidirectional(self):
        g = parse_flowchart("graph LR\n  A <--> B")
        assert g.edges[0].is_bidirectional is True

    def test_not_bidirectional(self):
        g = parse_flowchart("graph LR\n  A --> B")
        assert g.edges[0].is_bidirectional is False

    def test_self_reference(self):
        g = parse_flowchart("graph LR\n  A --> A")
        assert g.edges[0].is_self_reference is True

    def test_not_self_reference(self):
        g = parse_flowchart("graph LR\n  A --> B")
        assert g.edges[0].is_self_reference is False


# ── Comments ──────────────────────────────────────────────────────────────────

class TestComments:
    def test_full_line_comment(self):
        g = parse_flowchart("graph LR\n  %% comment\n  A --> B")
        assert len(g.edges) == 1

    def test_inline_comment(self):
        g = parse_flowchart("graph LR\n  A --> B %% comment")
        assert len(g.edges) == 1

    def test_multiple_comments(self):
        g = parse_flowchart(
            "graph LR\n  %% c1\n  A --> B\n  %% c2\n  B --> C"
        )
        assert len(g.edges) == 2

    def test_semicolon_inside_a_comment_stays_in_the_comment(self):
        g = parse_flowchart("graph LR\n  %% retry; then X --> Y\n  A --> B")
        assert list(g.nodes) == ["A", "B"]
        assert len(g.edges) == 1


# ── Semicolons ────────────────────────────────────────────────────────────────

class TestSemicolons:
    def test_semicolon_separation(self):
        g = parse_flowchart("graph LR\n  A --> B; B --> C")
        assert len(g.edges) == 2

    def test_trailing_semicolon(self):
        g = parse_flowchart("graph LR\n  A --> B;")
        assert len(g.edges) == 1


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_input(self):
        g = parse_flowchart("")
        assert len(g.nodes) == 0

    def test_header_only(self):
        g = parse_flowchart("graph LR")
        assert len(g.nodes) == 0

    def test_quoted_label_with_special_chars(self):
        g = parse_flowchart('graph LR\n  A["Hello (world)"]')
        assert g.nodes["A"].label == "Hello (world)"

    @pytest.mark.parametrize("br", ["<br>", "<br/>", "<br />", "<BR>"])
    def test_br_breaks_a_label_into_lines(self, br):
        g = parse_flowchart(f'graph LR\n  A["one{br}two"]\n  B@{{ shape: rect, label: "x{br}y" }}')
        assert g.nodes["A"].label == "one\\ntwo"
        assert g.nodes["B"].label == "x\\ny"

    @pytest.mark.parametrize("br", ["<br>", "<br/>", "<br />"])
    def test_br_in_an_unquoted_label(self, br):
        g = parse_flowchart(f"graph TD\n  A --> N[one{br}two]")
        assert set(g.nodes) == {"A", "N"}
        assert g.nodes["N"].label == "one\\ntwo"
        assert g.nodes["N"].shape == NodeShape.RECTANGLE
        assert (g.edges[0].source, g.edges[0].target) == ("A", "N")

    @pytest.mark.parametrize("label", ["x > 0", "a -> b", "a >= b"])
    def test_greater_than_in_an_unquoted_label(self, label):
        g = parse_flowchart(f"graph LR\n  A[{label}]")
        assert list(g.nodes) == ["A"]
        assert g.nodes["A"].label == label
        assert g.nodes["A"].shape == NodeShape.RECTANGLE

    def test_asymmetric_shape_still_parses(self):
        g = parse_flowchart("graph LR\n  A>flag] --> B>other one]")
        assert g.nodes["A"].shape == NodeShape.ASYMMETRIC and g.nodes["A"].label == "flag"
        assert g.nodes["B"].shape == NodeShape.ASYMMETRIC and g.nodes["B"].label == "other one"

    def test_unicode_label(self):
        g = parse_flowchart('graph LR\n  A["日本語"]')
        assert g.nodes["A"].label == "日本語"

    def test_node_order_preserved(self):
        g = parse_flowchart("graph LR\n  C --> A\n  B --> D")
        assert g.node_order == ["C", "A", "B", "D"]

    def test_get_roots(self):
        g = parse_flowchart("graph LR\n  A --> B\n  A --> C\n  B --> D")
        assert g.get_roots() == ["A"]

    def test_multiple_roots(self):
        g = parse_flowchart("graph LR\n  A --> C\n  B --> C")
        assert set(g.get_roots()) == {"A", "B"}

    def test_node_label_updated_on_redeclaration(self):
        g = parse_flowchart("graph LR\n  A --> B\n  A[Custom]")
        assert g.nodes["A"].label == "Custom"


class TestSemicolonStatements:
    def test_semicolon_inside_quoted_label_not_split(self):
        g = parse_flowchart('graph LR\n  A["a;b"] --> B')
        assert set(g.nodes) == {"A", "B"}
        assert g.nodes["A"].label == "a;b"
        assert len(g.edges) == 1

    def test_semicolon_still_splits_statements(self):
        g = parse_flowchart("graph LR; A --> B; B --> C")
        assert set(g.nodes) == {"A", "B", "C"}
        assert len(g.edges) == 2


class TestQuotedLabelText:
    def test_percent_pair_inside_quotes_is_label_text(self):
        g = parse_flowchart('graph LR\n  A["50%% off"] --> B')
        assert g.nodes["A"].label == "50%% off"
        assert [(e.source, e.target) for e in g.edges] == [("A", "B")]

    def test_comments_outside_quotes_still_stripped(self):
        g = parse_flowchart('graph LR\n  %% A --> C\n  A["50%% off"] --> B %% B --> D')
        assert set(g.nodes) == {"A", "B"}
        assert [(e.source, e.target) for e in g.edges] == [("A", "B")]

    def test_class_suffix_after_quoted_triple_colon(self):
        g = parse_flowchart('graph LR\n  A["x:::y"]:::hot')
        assert g.nodes["A"].label == "x:::y"
        assert g.nodes["A"].style_class == "hot"

    def test_triple_colon_inside_quotes_is_not_a_class(self):
        g = parse_flowchart('graph LR\n  A["x:::y"]')
        assert g.nodes["A"].label == "x:::y"
        assert g.nodes["A"].style_class is None


class TestEntityCodes:
    def test_mermaid_docs_example(self):
        g = parse_flowchart('graph LR\n  A["A double quote:#quot;"] --> B["A dec char:#9829;"]')
        assert g.nodes["A"].label == 'A double quote:"'
        assert g.nodes["B"].label == "A dec char:♥"

    def test_html_character_names(self):
        g = parse_flowchart('graph LR\n  A["Tom #amp; Jerry"] --> B["#lt;tag#gt;"]')
        assert g.nodes["A"].label == "Tom & Jerry"
        assert g.nodes["B"].label == "<tag>"

    def test_unknown_names_and_bare_hash_are_kept(self):
        g = parse_flowchart('graph LR\n  A["#notathing; and # sign"]')
        assert g.nodes["A"].label == "#notathing; and # sign"

    def test_edge_label(self):
        g = parse_flowchart('graph LR\n  A -->|"#quot;yes#quot;"| B')
        assert g.edges[0].label == '"yes"'

    def test_subgraph_title(self):
        g = parse_flowchart('graph LR\n  subgraph one ["Tom #amp; Jerry"]\n    A\n  end')
        assert g.subgraphs[0].label == "Tom & Jerry"

    def test_markdown_label(self):
        g = parse_flowchart('graph LR\n  A["`**#lt;b#gt;** #amp;`"]')
        assert g.nodes["A"].label == "<b> &"
        assert [s.text for s in g.nodes["A"].label_segments] == ["<b>", " &"]

    @pytest.mark.parametrize("code", ["#9;", "#10;", "#12;", "#13;", "#Tab;", "#NewLine;"])
    def test_whitespace_codes_become_a_space(self, code):
        g = parse_flowchart(f'graph LR\n  A["ab{code}cd"]')
        assert g.nodes["A"].label == "ab cd"

    def test_codes_for_control_characters_never_reach_the_output(self):
        codes = "".join(f"#{n};" for n in [*range(0x20), *range(0x7F, 0xA0)])
        source = f'graph LR\n  A["a{codes}b"] -->|"a{codes}b"| B\n  subgraph S["a{codes}b"]\n    C\n  end'
        g = parse_flowchart(source)
        for label in (g.nodes["A"].label, g.edges[0].label, g.subgraphs[0].label):
            assert not [hex(ord(c)) for c in label if ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F]
        output = render(source)
        assert not [hex(ord(c)) for c in output if c != "\n" and (ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F)]
