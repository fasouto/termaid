"""Tests for treemap diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.treemap import parse_treemap


# ── Parser tests ──────────────────────────────────────────────────────────────


class TestTreemapParser:
    def test_basic_flat_nodes(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "A": 10\n'
            '    "B": 20\n'
            '    "C": 30'
        )
        assert len(d.roots) == 3
        assert d.roots[0].label == "A"
        assert d.roots[0].value == 10
        assert d.roots[1].label == "B"
        assert d.roots[1].value == 20
        assert d.roots[2].label == "C"
        assert d.roots[2].value == 30

    def test_nested_sections(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "Section 1"\n'
            '        "Leaf 1.1": 12\n'
            '    "Section 2"\n'
            '        "Leaf 2.1": 20'
        )
        assert len(d.roots) == 2
        assert d.roots[0].label == "Section 1"
        assert len(d.roots[0].children) == 1
        assert d.roots[0].children[0].label == "Leaf 1.1"
        assert d.roots[0].children[0].value == 12
        assert d.roots[1].label == "Section 2"
        assert d.roots[1].children[0].label == "Leaf 2.1"

    def test_deep_nesting(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "L1"\n'
            '        "L2"\n'
            '            "L3": 5'
        )
        assert len(d.roots) == 1
        assert d.roots[0].children[0].children[0].label == "L3"
        assert d.roots[0].children[0].children[0].value == 5

    def test_section_total_value(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "Parent"\n'
            '        "A": 10\n'
            '        "B": 20'
        )
        assert d.roots[0].total_value == 30

    def test_total_value(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "A": 10\n'
            '    "B": 20'
        )
        assert d.total_value == 30

    def test_decimal_values(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "A": 12.5\n'
            '    "B": 7.5'
        )
        assert d.roots[0].value == 12.5
        assert d.roots[1].value == 7.5

    def test_comments_ignored(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    %% comment\n'
            '    "A": 10\n'
            '    %% another\n'
            '    "B": 20'
        )
        assert len(d.roots) == 2

    def test_empty_treemap(self):
        d = parse_treemap("treemap-beta")
        assert len(d.roots) == 0

    def test_section_without_value(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "Section"\n'
            '        "Leaf": 10'
        )
        assert d.roots[0].value == 0
        assert d.roots[0].total_value == 10

    def test_multiple_children(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "Parent"\n'
            '        "A": 5\n'
            '        "B": 10\n'
            '        "C": 15'
        )
        assert len(d.roots[0].children) == 3

    def test_sibling_sections(self):
        d = parse_treemap(
            'treemap-beta\n'
            '    "S1"\n'
            '        "A": 10\n'
            '    "S2"\n'
            '        "B": 20\n'
            '    "S3"\n'
            '        "C": 30'
        )
        assert len(d.roots) == 3
        for root in d.roots:
            assert len(root.children) == 1


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestTreemapRendering:
    def test_basic_renders_with_labels(self):
        output = render(
            'treemap-beta\n'
            '    "Frontend": 40\n'
            '    "Backend": 35\n'
            '    "Database": 25'
        )
        assert "Frontend" in output
        assert "Backend" in output
        assert "Database" in output

    def test_values_displayed_for_leaves(self):
        output = render(
            'treemap-beta\n'
            '    "A": 42\n'
            '    "B": 58'
        )
        assert "42" in output
        assert "58" in output

    def test_nested_labels_visible(self):
        output = render(
            'treemap-beta\n'
            '    "Section"\n'
            '        "Leaf": 10'
        )
        assert "Section" in output
        assert "Leaf" in output

    def test_ascii_mode(self):
        output = render(
            'treemap-beta\n'
            '    "A": 50\n'
            '    "B": 50',
            use_ascii=True,
        )
        assert "A" in output
        assert "B" in output
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋█▓░▒")
        for ch in output:
            assert ch not in unicode_chars

    def test_empty_treemap_renders(self):
        output = render("treemap-beta")
        assert isinstance(output, str)

    def test_proportional_sizing(self):
        """Larger values should get more space."""
        output = render(
            'treemap-beta\n'
            '    "Big": 90\n'
            '    "Small": 10'
        )
        lines = output.split("\n")
        # Find the widths of each section by counting characters in top borders
        big_cols = sum(1 for line in lines if "Big" in line)
        small_cols = sum(1 for line in lines if "Small" in line)
        # Big should appear in at least as many lines as Small
        assert big_cols >= small_cols

    def test_leaf_nodes_solid_borders(self):
        output = render(
            'treemap-beta\n'
            '    "A": 50\n'
            '    "B": 50'
        )
        # Leaf nodes use solid borders
        assert "─" in output
        assert "│" in output

    def test_section_nodes_dashed_borders(self):
        output = render(
            'treemap-beta\n'
            '    "Parent"\n'
            '        "Child": 10'
        )
        # Section nodes use dashed borders
        assert "┄" in output
        assert "┆" in output
        # Children use solid borders
        assert "─" in output
        assert "│" in output

    def test_single_node(self):
        output = render(
            'treemap-beta\n'
            '    "Only": 100'
        )
        assert "Only" in output
        assert "100" in output

    def test_many_nodes(self):
        lines = ['treemap-beta']
        for i in range(5):
            lines.append(f'    "Item{i}": 20')
        output = render("\n".join(lines))
        # All equal-sized nodes should fit
        for i in range(5):
            assert f"Item{i}" in output

    def test_frontmatter_with_treemap(self):
        output = render(
            '---\nconfig:\n  treemap:\n    padding: 2\n---\n'
            'treemap-beta\n'
            '    "A": 60\n'
            '    "B": 40'
        )
        assert "A" in output
        assert "B" in output


class TestTreemapWideChars:
    def test_cjk_label_does_not_overflow_box(self):
        from termaid.utils import display_width
        output = render(
            'treemap-beta\n'
            '  "中文很长的标签名称测试"\n'
            '    "甲": 40\n'
            '    "乙": 10'
        )
        lines = output.split("\n")
        border_w = max(display_width(l) for l in lines if "┌" in l or "┄" in l)
        assert all(display_width(l) <= border_w for l in lines)
