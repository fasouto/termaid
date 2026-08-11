"""End-to-end integration tests: mermaid string in, correct unicode out.

These test the full pipeline from parsing through rendering and verify
structural properties of the output.
"""
from __future__ import annotations

import pytest

from termaid import render, parse
from tests.conftest import (
    assert_all_nodes_rendered,
    assert_no_edge_node_overlap,
    assert_reasonable_dimensions,
    assert_valid_unicode,
)


class TestBasicRendering:
    def test_simple_lr(self):
        output = render("graph LR\n  A --> B")
        assert "A" in output
        assert "B" in output
        assert "►" in output  # Arrow

    def test_simple_td(self):
        output = render("graph TD\n  A --> B")
        assert "A" in output
        assert "B" in output
        assert "▼" in output  # Down arrow

    def test_empty_graph(self):
        output = render("graph LR\n  A")
        assert "A" in output
        # No arrows for single node
        assert "►" not in output

    def test_chain(self):
        output = render("graph LR\n  A --> B --> C --> D --> E")
        for label in ["A", "B", "C", "D", "E"]:
            assert label in output

    def test_render_returns_string(self):
        result = render("graph LR\n  A --> B")
        assert isinstance(result, str)
        assert len(result) > 0


class TestAllDirections:
    def test_lr(self):
        output = render("graph LR\n  A --> B")
        lines = output.split("\n")
        # In LR, A and B should be on the same row
        a_row = next(i for i, l in enumerate(lines) if "A" in l)
        b_row = next(i for i, l in enumerate(lines) if "B" in l)
        assert a_row == b_row

    def test_td(self):
        output = render("graph TD\n  A --> B")
        lines = output.split("\n")
        a_row = next(i for i, l in enumerate(lines) if "A" in l)
        b_row = next(i for i, l in enumerate(lines) if "B" in l)
        assert a_row < b_row

    def test_bt(self):
        output = render("graph BT\n  A --> B")
        lines = output.split("\n")
        a_row = next(i for i, l in enumerate(lines) if "A" in l)
        b_row = next(i for i, l in enumerate(lines) if "B" in l)
        # In BT, A should be below B (flow goes up)
        assert a_row > b_row

    def test_rl(self):
        output = render("graph RL\n  A --> B")
        lines = output.split("\n")
        # In RL, A should be to the right of B
        a_line = next(l for l in lines if "A" in l)
        b_line = next(l for l in lines if "B" in l)
        assert a_line.index("A") > b_line.index("B") or a_line == b_line


class TestNodeShapes:
    def test_all_basic_shapes_render(self):
        """Each shape type should render with its label visible."""
        shapes = [
            ("A[Rectangle]", "Rectangle"),
            ("B(Rounded)", "Rounded"),
            ("C{Diamond}", "Diamond"),
            ("D([Stadium])", "Stadium"),
            ("E[[Subroutine]]", "Subroutine"),
            ("F((Circle))", "Circle"),
        ]
        for shape_def, label in shapes:
            source = f"graph LR\n  {shape_def}"
            output = render(source)
            assert label in output, f"Shape {shape_def} should render label '{label}'"

    def test_mixed_shapes_in_graph(self):
        output = render(
            "graph LR\n"
            "  A[Start] --> B{Decision}\n"
            "  B --> C(Process)\n"
            "  B --> D([End])"
        )
        for label in ["Start", "Decision", "Process", "End"]:
            assert label in output


class TestEdgeTypes:
    def test_solid_arrow(self):
        output = render("graph LR\n  A --> B")
        assert "►" in output

    def test_dotted_arrow(self):
        output = render("graph LR\n  A -.-> B")
        assert "┄" in output, "Dotted arrow should use ┄ character"
        assert "►" in output, "Dotted arrow should have arrowhead"

    def test_thick_arrow(self):
        output = render("graph LR\n  A ==> B")
        assert "━" in output, "Thick arrow should use ━ character"
        assert "►" in output, "Thick arrow should have arrowhead"

    def test_mixed_styles(self):
        output = render("graph LR\n  A --> B\n  B -.-> C\n  C ==> D")
        for label in ["A", "B", "C", "D"]:
            assert label in output


class TestEdgeLabels:
    def test_label_no_overlap(self):
        """Regression: parallel labeled edges should not truncate or overlap labels."""
        output = render(
            "graph TD\n"
            "    A -->|label one| C\n"
            "    B -->|label two| D\n"
            "    A --> D\n"
            "    B --> C"
        )
        # Both full label texts must be present (allowing for space-to-dash)
        assert "label" in output
        # "label two" should not be truncated — check "two" appears
        assert "two" in output
        assert "one" in output

    def test_three_labels_from_same_source(self):
        """Multiple labeled edges from one source should all be visible."""
        output = render(
            "graph TD\n"
            "    A[Start] -->|Yes| B[Process]\n"
            "    A -->|No| C[Error]\n"
            "    A -->|Maybe| D[Retry]"
        )
        assert "Yes" in output
        assert "No" in output
        assert "Maybe" in output

    def test_labels_avoid_protected_nodes_and_routed_edges(self):
        """Labels must move intact instead of leaving fragments over protected cells."""
        output = render(
            "flowchart LR\n"
            "    User[User question] --> Model[Model]\n"
            "    Model -->|search_web queries| Search[Internal search_web path]\n"
            "    Search -->|results and reference IDs| Model\n"
            "    Model -->|open ref_id list| Open[open runtime]\n"
            "    Model -->|open direct URL| Open\n"
            "    Open -->|page content with source identity| Model\n"
            "    Model --> Answer[Grounded answer]",
            padding_x=2,
            padding_y=0,
            gap=4,
        )

        for label in (
            "search_web queries",
            "results and reference IDs",
            "open ref_id list",
            "open direct URL",
            "page content with source identity",
        ):
            assert label in output

    def test_dotted_labels_avoid_crossing_routes(self):
        """Dotted edge labels must remain intact around dense crossing routes."""
        output = render(
            "flowchart LR\n"
            "    Search[Internal search_web] --> Grounding[Conversation grounding and citations]\n"
            "    Grounding -. missing bridge .-> LuminaState[Lumina page-context state]\n"
            "    Outputs[IToolExecutionOutputCollection] -. currently null on EDTI .-> Open[WebOpenToolExecutor]\n"
            "    LuminaState --> Open\n"
            "    Open --> Result[WebOpenResult]\n"
            "    Result -. missing EDTI citation stage .-> CitationState[Registered citation state]",
            padding_x=2,
            padding_y=0,
            gap=4,
        )

        assert "missing bridge" in output
        assert "currently null on EDTI" in output
        assert "missing EDTI citation stage" in output


class TestSubgraphs:
    def test_basic_subgraph(self):
        output = render(
            "graph LR\n"
            "  subgraph one\n"
            "    A --> B\n"
            "  end"
        )
        assert "A" in output
        assert "B" in output

    def test_subgraph_label_visible(self):
        output = render(
            "graph LR\n"
            "  subgraph Frontend\n"
            "    UI\n"
            "  end"
        )
        assert "Frontend" in output
        assert "UI" in output


class TestSelfReference:
    def test_self_loop_renders(self):
        output = render("graph LR\n  A --> A")
        assert "A" in output
        assert len(output.split("\n")) > 1  # More than one line (loop visible)

    def test_self_with_other_edge(self):
        output = render("graph LR\n  A --> A\n  A --> B")
        assert "A" in output
        assert "B" in output


class TestCycle:
    def test_cycle_renders(self):
        output = render("graph LR\n  A --> B --> C --> A")
        for label in ["A", "B", "C"]:
            assert label in output
        assert_reasonable_dimensions(output)

    def test_complex_cycle(self):
        output = render(
            "graph LR\n"
            "  A --> B\n  B --> C\n  C --> D\n  D --> A"
        )
        for label in ["A", "B", "C", "D"]:
            assert label in output


class TestBranching:
    def test_ampersand_rhs(self):
        output = render("graph LR\n  A --> B & C")
        assert_all_nodes_rendered(output, ["A", "B", "C"])

    def test_ampersand_lhs(self):
        output = render("graph LR\n  A & B --> C")
        assert_all_nodes_rendered(output, ["A", "B", "C"])

    def test_ampersand_both(self):
        output = render("graph LR\n  A & B --> C & D")
        assert_all_nodes_rendered(output, ["A", "B", "C", "D"])

    def test_fan_in_td(self):
        output = render("graph TD\n  A & B & C --> D")
        assert_all_nodes_rendered(output, ["A", "B", "C", "D"])

    def test_fan_out_td(self):
        output = render("graph TD\n  A --> B & C & D")
        assert_all_nodes_rendered(output, ["A", "B", "C", "D"])


class TestAsciiMode:
    def test_ascii_basic(self):
        output = render("graph LR\n  A --> B", use_ascii=True)
        assert "+" in output  # ASCII corner
        assert ">" in output  # ASCII arrow

    def test_ascii_no_unicode(self):
        output = render("graph LR\n  A --> B --> C", use_ascii=True)
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋")
        for ch in output:
            assert ch not in unicode_chars, f"Unicode char '{ch}' in ASCII output"


class TestPadding:
    def test_custom_padding(self):
        small = render("graph LR\n  A --> B", padding_x=2, padding_y=1)
        large = render("graph LR\n  A --> B", padding_x=8, padding_y=4)
        # Larger padding should produce larger output
        assert len(large) > len(small)


class TestParseAPI:
    def test_parse_returns_graph(self):
        g = parse("graph LR\n  A --> B")
        assert "A" in g.nodes
        assert "B" in g.nodes
        assert len(g.edges) == 1


class TestComments:
    def test_comments_ignored(self):
        output = render("graph LR\n  %% comment\n  A --> B\n  %% another")
        assert "A" in output
        assert "B" in output
        assert "%%" not in output


class TestComplexGraphs:
    """Tests from the Mermaid documentation examples."""

    def test_mermaid_comprehensive(self):
        output = render(
            "flowchart LR\n"
            "    A[Hard edge] -->|Link text| B(Round edge)\n"
            "    B --> C{Decision}\n"
            "    C -->|One| D[Result one]\n"
            "    C -->|Two| E[Result two]"
        )
        for label in ["Hard edge", "Round edge", "Decision", "Result one", "Result two"]:
            assert label in output
        assert_valid_unicode(output)
        assert_reasonable_dimensions(output)

    def test_mermaid_decision_flow(self):
        output = render(
            "flowchart TD\n"
            "    A[Start] --> B{Is it?}\n"
            "    B -->|Yes| C[OK]\n"
            "    C --> D[Rethink]\n"
            "    D --> B\n"
            "    B -->|No| E[End]"
        )
        for label in ["Start", "Is it?", "OK", "Rethink", "End"]:
            assert label in output

    def test_three_subgraphs(self):
        output = render(
            "flowchart TB\n"
            "    c1-->a2\n"
            "    subgraph one\n"
            "    a1-->a2\n"
            "    end\n"
            "    subgraph two\n"
            "    b1-->b2\n"
            "    end\n"
            "    subgraph three\n"
            "    c1-->c2\n"
            "    end"
        )
        for label in ["a1", "a2", "b1", "b2", "c1", "c2"]:
            assert label in output

    def test_link_styles(self):
        """Test all link styles render with correct line characters."""
        output_solid = render("flowchart LR\n    A-->B")
        assert "─" in output_solid, "Solid link should use ─"

        output_open = render("flowchart LR\n    A --- B")
        assert "─" in output_open, "Open link should use ─"
        assert "►" not in output_open, "Open link should not have arrowhead"

        output_dotted = render("flowchart LR\n    A -.-> B")
        assert "┄" in output_dotted, "Dotted link should use ┄"

        output_thick = render("flowchart LR\n    A ==> B")
        assert "━" in output_thick, "Thick link should use ━"

    def test_chained_links(self):
        output = render("flowchart LR\n   A -- text --> B -- text2 --> C")
        assert "A" in output
        assert "C" in output
        assert "text" in output

    def test_semicolon_separation(self):
        output = render("graph LR\n  A --> B; B --> C; C --> D")
        for label in ["A", "B", "C", "D"]:
            assert label in output
