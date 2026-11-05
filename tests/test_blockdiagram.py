"""Tests for block diagram parsing and rendering."""
from __future__ import annotations

import time

import pytest

from termaid import render
from termaid.parser.blockdiagram import parse_block_diagram


# ── Parser tests ──────────────────────────────────────────────────────────────


class TestBlockDiagramParser:
    def test_basic_blocks(self):
        d = parse_block_diagram(
            "block-beta\n"
            '  A["Hello"]\n'
            '  B["World"]'
        )
        assert len(d.blocks) == 2
        assert d.blocks[0].id == "A"
        assert d.blocks[0].label == "Hello"

    def test_columns_directive(self):
        d = parse_block_diagram(
            "block-beta\n"
            "  columns 3\n"
            '  A["X"] B["Y"] C["Z"]'
        )
        assert d.columns == 3

    def test_block_with_shape(self):
        d = parse_block_diagram(
            "block-beta\n"
            '  A("Rounded")'
        )
        assert d.blocks[0].shape == "rounded"

    def test_block_with_col_span(self):
        d = parse_block_diagram(
            "block-beta\n"
            "  columns 3\n"
            '  A["Wide"]:2\n'
            '  B["Normal"]'
        )
        assert d.blocks[0].col_span == 2
        assert d.blocks[1].col_span == 1

    def test_space_block(self):
        d = parse_block_diagram(
            "block-beta\n"
            "  columns 2\n"
            "  space\n"
            '  A["Hello"]'
        )
        assert d.blocks[0].is_space is True
        assert d.blocks[1].is_space is False

    def test_links(self):
        d = parse_block_diagram(
            "block-beta\n"
            '  A["X"]\n'
            '  B["Y"]\n'
            "  A --> B"
        )
        assert len(d.links) == 1
        assert d.links[0].source == "A"
        assert d.links[0].target == "B"

    def test_block_keyword(self):
        """Both 'block-beta' and 'block' should work."""
        d = parse_block_diagram(
            "block-beta\n"
            '  A["Test"]'
        )
        assert len(d.blocks) == 1

    def test_multiple_blocks_on_line(self):
        d = parse_block_diagram(
            "block-beta\n"
            "  columns 3\n"
            '  A["X"] B["Y"] C["Z"]'
        )
        assert len(d.blocks) == 3


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestBlockDiagramRendering:
    def test_basic_renders(self):
        output = render(
            "block-beta\n"
            '  A["Hello"]'
        )
        assert "Hello" in output
        assert "┌" in output

    def test_columns_layout(self):
        output = render(
            "block-beta\n"
            "  columns 3\n"
            '  A["Frontend"] B["API"] C["Database"]'
        )
        assert "Frontend" in output
        assert "API" in output
        assert "Database" in output
        # All should be on the same row
        lines = output.split("\n")
        api_line = next(l for l in lines if "API" in l)
        assert "Frontend" in api_line
        assert "Database" in api_line

    def test_box_borders(self):
        output = render(
            "block-beta\n"
            '  A["Test"]'
        )
        assert "┌" in output
        assert "┘" in output
        assert "─" in output
        assert "│" in output

    def test_multiple_rows(self):
        output = render(
            "block-beta\n"
            "  columns 2\n"
            '  A["A"] B["B"]\n'
            '  C["C"] D["D"]'
        )
        assert "A" in output
        assert "B" in output
        assert "C" in output
        assert "D" in output

    def test_ascii_mode(self):
        output = render(
            "block-beta\n"
            "  columns 2\n"
            '  A["Hello"] B["World"]',
            use_ascii=True,
        )
        assert "Hello" in output
        assert "World" in output
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋")
        for ch in output:
            assert ch not in unicode_chars

    def test_space_block_creates_gap(self):
        output = render(
            "block-beta\n"
            "  columns 3\n"
            '  A["Left"] space B["Right"]'
        )
        assert "Left" in output
        assert "Right" in output
        # Space block should not have its own label rendered
        lines = output.split("\n")
        # Both blocks should be rendered
        assert any("Left" in l and "Right" in l for l in lines)

    def test_col_span_wider_blocks(self):
        output = render(
            "block-beta\n"
            "  columns 3\n"
            '  A["Wide"]:2 B["Normal"]\n'
            '  C["One"] D["Two"] E["Three"]'
        )
        assert "Wide" in output
        assert "Normal" in output

    def test_link_arrows_between_blocks(self):
        output = render(
            "block-beta\n"
            '  A["Source"]\n'
            '  B["Target"]\n'
            "  A-->B"
        )
        assert "Source" in output
        assert "Target" in output
        assert "►" in output or ">" in output, "Arrow should be rendered between blocks"


class TestNestedGroups:
    def test_doubly_nested_blocks_are_rendered(self):
        output = render(
            "block-beta\n"
            "  block:outer\n"
            "    block:inner\n"
            "      a\n"
            "      b\n"
            "    end\n"
            "    c\n"
            "  end"
        )
        assert "a" in output
        assert "b" in output
        assert "c" in output

    def test_deep_nesting_renders_quickly(self):
        # Deep enough that doubling work per level takes many seconds, shallow
        # enough that a regression fails here instead of hanging CI.
        depth = 22
        source = "block-beta\n" + "".join("  " * d + f"block:g{d}\n" for d in range(depth))
        source += "  " * depth + "X\n" + "".join("  " * d + "end\n" for d in reversed(range(depth)))
        start = time.perf_counter()
        output = render(source)
        assert time.perf_counter() - start < 2, "22 nested groups should not take seconds"
        assert "X" in output


class TestOversizedGrids:
    def test_huge_column_count_draws_like_the_cap(self):
        assert render("block-beta\ncolumns 50000\nA") == render("block-beta\ncolumns 64\nA")

    def test_columns_just_past_the_cap_draw_like_trunk(self):
        assert render("block-beta\ncolumns 65\nA B C") == render("block-beta\ncolumns 64\nA B C")

    @pytest.mark.parametrize("source", [
        "block-beta\ncolumns 1000000\nA",
        "block-beta\nA:1000000",
        "block-beta\nspace:1000000\nA",
        "block-beta\nblock:g\ncolumns 1000000\nA\nend",
    ], ids=["columns", "span", "space", "nested-columns"])
    def test_absurd_sizes_render_quickly(self, source):
        start = time.perf_counter()
        output = render(source)
        assert time.perf_counter() - start < 2, "an absurd grid size should be capped, not drawn"
        assert output.strip()

    def test_wide_blocks_without_columns_wrap_at_the_cap(self):
        output = render("block-beta\n" + "\n".join(f"B{i}:64" for i in range(3)))
        assert max(len(line) for line in output.split("\n")) < 1100
        assert all(f"B{i}" in output for i in range(3))
