"""Tests for mindmap parsing and rendering."""
from __future__ import annotations

import pytest

from termaid import render
from termaid.parser.mindmap import parse_mindmap


class TestMindmapParser:
    """Test mindmap syntax parsing."""

    def test_simple_tree(self):
        mm = parse_mindmap("mindmap\n  Root\n    A\n    B")
        assert mm.root is not None
        assert mm.root.label == "Root"
        assert len(mm.root.children) == 2
        assert mm.root.children[0].label == "A"
        assert mm.root.children[1].label == "B"

    def test_nested(self):
        mm = parse_mindmap("mindmap\n  R\n    A\n      A1\n      A2\n    B")
        assert mm.root.label == "R"
        assert len(mm.root.children) == 2
        a = mm.root.children[0]
        assert a.label == "A"
        assert len(a.children) == 2
        assert a.children[0].label == "A1"

    def test_empty(self):
        mm = parse_mindmap("mindmap")
        assert mm.root is None

    def test_single_node(self):
        mm = parse_mindmap("mindmap\n  Only")
        assert mm.root.label == "Only"
        assert mm.root.children == []

    def test_strips_round_shape(self):
        mm = parse_mindmap("mindmap\n  (Round)")
        assert mm.root.label == "Round"

    def test_strips_square_shape(self):
        mm = parse_mindmap("mindmap\n  [Square]")
        assert mm.root.label == "Square"

    def test_strips_hexagon_shape(self):
        mm = parse_mindmap("mindmap\n  {{Hex}}")
        assert mm.root.label == "Hex"

    def test_comments_ignored(self):
        mm = parse_mindmap("mindmap\n  Root %% comment\n    Child")
        assert mm.root.label == "Root"
        assert len(mm.root.children) == 1

    def test_blank_lines_ignored(self):
        mm = parse_mindmap("mindmap\n  Root\n\n    Child\n\n    Other")
        assert len(mm.root.children) == 2

    def test_depth_property(self):
        mm = parse_mindmap("mindmap\n  R\n    A\n      B\n        C")
        assert mm.root.depth == 3


class TestMindmapRendering:
    """Test mindmap rendering output."""

    def test_single_node_renders(self):
        out = render("mindmap\n  Hello")
        assert "Hello" in out

    def test_all_children_visible(self):
        out = render("mindmap\n  Root\n    Alpha\n    Beta\n    Gamma")
        for label in ["Root", "Alpha", "Beta", "Gamma"]:
            assert label in out, f"{label} missing from output"

    def test_nested_children_visible(self):
        out = render("mindmap\n  R\n    A\n      A1\n      A2\n    B")
        for label in ["R", "A", "A1", "A2", "B"]:
            assert label in out

    def test_branch_characters_present(self):
        out = render("mindmap\n  R\n    A\n    B")
        assert "╭" in out or "├" in out
        assert "╰" in out

    def test_overflow_to_left(self):
        """Many children should spill some to the left side."""
        children = "\n".join(f"    C{i}" for i in range(9))
        out = render(f"mindmap\n  Center\n{children}")
        # Left-branching uses ┐ or ┘ connectors
        assert "┐" in out or "┘" in out or "┤" in out

    def test_deep_nesting_no_crash(self):
        """5 levels deep should render without errors."""
        src = "mindmap\n  L0\n    L1\n      L2\n        L3\n          L4\n            L5"
        out = render(src)
        assert "L5" in out

    def test_no_crash_on_empty(self):
        out = render("mindmap")
        assert isinstance(out, str)


class TestNodeShapes:
    """A node written with an id and a shape shows only its text."""

    @pytest.mark.parametrize("written", [
        "root((termaid))", "((termaid))", "root(termaid)", "(termaid)", "root[termaid]",
        "[termaid]", "root{{termaid}}", "root)termaid(", "root))termaid((", 'root["termaid"]',
    ])
    def test_shape_and_id_are_not_drawn(self, written):
        out = render(f"mindmap\n  {written}\n    Library\n")
        assert out.split("\n")[0].startswith("termaid ──"), out

    def test_plain_text_with_brackets_inside_is_kept(self):
        out = render("mindmap\n  root\n    call f(x) now\n")
        assert "call f(x) now" in out

    def test_icon_and_class_lines_are_not_nodes(self):
        out = render("mindmap\n  root((termaid))\n    Library\n    ::icon(fa fa-book)\n    :::urgent\n")
        assert "icon" not in out and "urgent" not in out and "Library" in out


class TestMindmapLabelText:
    """Mermaid draws Markdown strings and <br> as formatted text, and never draws meta lines."""

    def test_markdown_strings_print_their_text(self):
        out = render(
            'mindmap\n'
            '    id1["`**Root** with\n'
            'a second line`"]\n'
            '      id2["`The dog in **the** hog`"]\n'
            '      id3[Regular label]\n'
        )
        assert "`" not in out and "*" not in out and "id1" not in out
        assert "The dog in the hog" in out
        rows = out.splitlines()
        root_row = next(i for i, row in enumerate(rows) if "Root with" in row)
        assert "a second line" in rows[root_row + 1]
        assert "a second line" not in rows[root_row]

    def test_br_breaks_a_label(self):
        out = render("mindmap\n  root[One<br/>Two]\n    Leaf\n")
        assert "<br" not in out
        assert [row.strip()[:3] for row in out.splitlines()[:2]] == ["One", "Two"]

    def test_meta_lines_are_not_nodes(self):
        mm = parse_mindmap(
            "mindmap\n"
            "  accTitle: Plans\n"
            "  accDescr { Many\n"
            "  lines }\n"
            "  root((Plans))\n"
            "    A\n"
        )
        assert mm.root.label == "Plans"
        assert [c.label for c in mm.root.children] == ["A"]
