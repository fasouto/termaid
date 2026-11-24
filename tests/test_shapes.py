"""Comprehensive node shape tests.

Tests all supported shapes: rectangle, rounded, stadium, subroutine,
diamond, hexagon, circle, double_circle, asymmetric, cylinder,
parallelogram, parallelogram_alt, trapezoid, trapezoid_alt.
"""
from __future__ import annotations

import pytest

from termaid import render
from termaid.parser.flowchart import parse_flowchart
from termaid.graph.shapes import NodeShape


# ── Parser shape detection ────────────────────────────────────────────────────

class TestShapeParsing:
    """Verify parser correctly identifies all shape types."""

    @pytest.mark.parametrize("syntax,expected_shape", [
        ("A[text]", NodeShape.RECTANGLE),
        ("A(text)", NodeShape.ROUNDED),
        ("A([text])", NodeShape.STADIUM),
        ("A[[text]]", NodeShape.SUBROUTINE),
        ("A{text}", NodeShape.DIAMOND),
        ("A{{text}}", NodeShape.HEXAGON),
        ("A((text))", NodeShape.CIRCLE),
        ("A(((text)))", NodeShape.DOUBLE_CIRCLE),
        ("A>text]", NodeShape.ASYMMETRIC),
        ("A[(text)]", NodeShape.CYLINDER),
        (r"A[/text\]", NodeShape.TRAPEZOID),
        (r"A[\text/]", NodeShape.TRAPEZOID_ALT),
        ("A[/text/]", NodeShape.PARALLELOGRAM),
        (r"A[\text\]", NodeShape.PARALLELOGRAM_ALT),
    ])
    def test_shape_detection(self, syntax: str, expected_shape: NodeShape):
        g = parse_flowchart(f"graph LR\n  {syntax}")
        assert g.nodes["A"].shape == expected_shape

    def test_plain_node_defaults_to_rectangle(self):
        g = parse_flowchart("graph LR\n  A")
        assert g.nodes["A"].shape == NodeShape.RECTANGLE


# ── Shape rendering ───────────────────────────────────────────────────────────

class TestShapeRendering:
    """Verify all shapes render without errors and produce visible output."""

    ALL_SHAPES = [
        ("A[Rectangle]", "Rectangle"),
        ("A(Rounded)", "Rounded"),
        ("A([Stadium])", "Stadium"),
        ("A[[Subroutine]]", "Subroutine"),
        ("A{Diamond}", "Diamond"),
        ("A{{Hexagon}}", "Hexagon"),
        ("A((Circle))", "Circle"),
        ("A(((Double)))", "Double"),
        ("A>Asym]", "Asym"),
        ("A[(Database)]", "Database"),
        (r"A[/Trap\]", "Trap"),
        (r"A[\AltT/]", "AltT"),
        ("A[/Para/]", "Para"),
        (r"A[\AltP\]", "AltP"),
    ]

    @pytest.mark.parametrize("syntax,label", ALL_SHAPES)
    def test_shape_renders(self, syntax: str, label: str):
        output = render(f"graph LR\n  {syntax}")
        assert label in output, f"Shape {syntax} should render label '{label}'"
        assert len(output.strip()) > 0

    @pytest.mark.parametrize("syntax,label", ALL_SHAPES)
    def test_shape_renders_ascii(self, syntax: str, label: str):
        output = render(f"graph LR\n  {syntax}", use_ascii=True)
        assert label in output

    def test_rectangle_has_square_corners(self):
        output = render("graph LR\n  A[Hello]")
        assert "┌" in output
        assert "┐" in output
        assert "└" in output
        assert "┘" in output

    def test_rounded_has_round_corners(self):
        output = render("graph LR\n  A(Hello)")
        assert "╭" in output
        assert "╯" in output

    def test_diamond_has_marker(self):
        output = render("graph LR\n  A{Decision}")
        assert "◇" in output

    def test_stadium_has_parens(self):
        output = render("graph LR\n  A([Stadium])")
        assert "(" in output
        assert ")" in output

    def test_hexagon_has_slashes(self):
        output = render("graph LR\n  A{{Hex}}")
        assert "Hex" in output
        assert "/" in output, "Hexagon should render with / character"
        assert "\\" in output, "Hexagon should render with \\ character"

    def test_cylinder_has_rounded_top(self):
        output = render("graph LR\n  A[(DB)]")
        assert "DB" in output
        # Cylinder uses rounded corners for the curved top
        assert "╭" in output, "Cylinder should have rounded top"
        assert "╰" in output, "Cylinder should have rounded bottom"

    def test_cylinder_lid_sits_inside_the_body(self):
        lines = render("graph LR\n  A[(DB)]").split("\n")
        ascii_lines = render("graph LR\n  A[(DB)]", use_ascii=True).split("\n")
        assert (lines[0].strip(), lines[1].strip()) == ("╭──────╮", "│╰────╯│")
        assert (ascii_lines[0].strip(), ascii_lines[1].strip()) == ("+------+", "|\\____/|")

    def test_all_shapes_in_one_graph(self):
        """All shapes in a single graph should render without errors."""
        output = render(
            "graph TD\n"
            "  A[Rect] --> B(Round)\n"
            "  B --> C{Diamond}\n"
            "  C --> D([Stadium])\n"
            "  D --> E[[Sub]]\n"
            "  E --> F((Circle))\n"
        )
        for label in ["Rect", "Round", "Diamond", "Stadium", "Sub", "Circle"]:
            assert label in output


class TestCylinderLabelKeepsOffTheLid:
    """The lid's rim has a row of its own at every padding (issue #47)."""

    @pytest.mark.parametrize("padding_y", [0, 1, 2, 3])
    @pytest.mark.parametrize("label,lines", [("Store", ["Store"]), ("one<br/>two", ["one", "two"])])
    def test_no_label_text_on_the_rim_row(self, padding_y, label, lines):
        out = render(f'flowchart LR\n  A[("{label}")]', padding_y=padding_y).split("\n")
        rim = next(i for i, row in enumerate(out) if "╰" in row and "╯" in row and "│" in row)
        assert rim == 1
        assert set(out[rim].strip()) <= set("│╰─╯"), out
        below = [row.strip("│ ") for row in out[rim + 1:]]
        assert [row for row in below if row and not set(row) <= set("╰─╯")] == lines

    def test_the_most_compact_cylinder_is_four_rows(self):
        out = render('flowchart LR\n  A[("Store")]', padding_y=0).split("\n")
        assert [row for row in out if row.strip()] == [
            "╭─────────╮",
            "│╰───────╯│",
            "│  Store  │",
            "╰─────────╯",
        ]

    def test_the_default_cylinder_is_unchanged(self):
        out = render('flowchart LR\n  A[("Store")]').split("\n")
        assert out[2].strip("│ ") == "Store" and len([row for row in out if row.strip()]) == 5
