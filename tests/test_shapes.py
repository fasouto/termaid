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

    def test_stadium_is_a_capsule(self):
        lines = render("graph LR\n  A([Stadium])").split("\n")
        assert lines[0].strip().startswith("╭") and lines[0].startswith(" ")  # inset corner
        assert lines[1].lstrip().startswith("╭╯") and lines[1].rstrip().endswith("╰╮")
        assert "│  Stadium  │" in lines[2]
        assert lines[3].lstrip().startswith("╰╮") and lines[3].rstrip().endswith("╭╯")

    def test_short_stadium_has_round_sides(self):
        # Too short for a capsule: a rounded box with round ends for sides.
        lines = render("graph LR\n  A([Stadium])", padding_y=0).split("\n")
        assert lines[0].startswith("╭") and lines[0].rstrip().endswith("╮")
        assert lines[1].startswith("❨  Stadium") and lines[1].rstrip().endswith("❩")
        assert lines[2].startswith("╰")

    def test_ascii_stadium(self):
        lines = render("graph LR\n  A([Stadium])", use_ascii=True).split("\n")
        assert lines[1].lstrip().startswith("/") and lines[3].lstrip().startswith("\\")
        assert "|  Stadium  |" in lines[2]
        short = render("graph LR\n  A([Stadium])", use_ascii=True, padding_y=0)
        assert "(  Stadium  )" in short

    def test_stadium_edges_attach_to_straight_sides(self):
        for padding_y in (0, 1, 2, 3):
            output = render("graph LR\n  A([Go]) --> B([Stop])", padding_y=padding_y)
            edge_row = next(line for line in output.split("\n") if "►" in line)
            assert "├─" in edge_row or "❩─" in edge_row, (padding_y, output)

    def test_cylinder_lid_never_covers_label(self):
        for padding_y in (0, 1, 2):
            for label in ("Database", "Users\\ntable"):
                output = render(f"graph LR\n  A[({label})]", padding_y=padding_y)
                for line in label.split("\\n"):
                    assert line in output, (padding_y, label, output)

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
