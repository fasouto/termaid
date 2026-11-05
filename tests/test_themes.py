"""Tests for the theme system and Rich rendering."""
from __future__ import annotations

import pytest

from termaid.renderer.themes import THEMES, get_theme, Theme


class TestThemeRegistry:
    """Test theme definitions."""

    EXPECTED_THEMES = ["default", "terra", "neon", "mono", "amber", "phosphor"]

    @pytest.mark.parametrize("name", EXPECTED_THEMES)
    def test_theme_exists(self, name: str):
        assert name in THEMES

    @pytest.mark.parametrize("name", EXPECTED_THEMES)
    def test_theme_has_all_fields(self, name: str):
        th = THEMES[name]
        assert th.name == name
        assert th.node
        assert th.edge
        assert th.arrow
        assert th.subgraph
        assert th.label
        assert th.edge_label
        assert th.subgraph_label

    def test_get_theme_returns_named(self):
        th = get_theme("terra")
        assert th.name == "terra"

    def test_get_theme_fallback(self):
        th = get_theme("nonexistent")
        assert th.name == "default"

    def test_themes_are_frozen(self):
        th = get_theme("default")
        with pytest.raises(AttributeError):
            th.node = "red"  # type: ignore


class TestCanvasStyleGrid:
    """Test that canvas style grid works correctly."""

    def test_style_grid_initialized(self):
        from termaid.renderer.canvas import Canvas
        c = Canvas(10, 5)
        assert c.get_style(0, 0) == "default"

    def test_put_with_style(self):
        from termaid.renderer.canvas import Canvas
        c = Canvas(10, 5)
        c.put(0, 0, "X", style="node")
        assert c.get_style(0, 0) == "node"

    def test_to_styled_pairs(self):
        from termaid.renderer.canvas import Canvas
        c = Canvas(5, 3)
        c.put(0, 0, "A", style="node")
        c.put(0, 1, "─", style="edge")
        pairs = c.to_styled_pairs()
        assert pairs[0][0] == ("A", "node")
        assert pairs[0][1] == ("─", "edge")

    def test_styles_in_rendered_output(self):
        """Verify style keys are set during rendering."""
        from termaid import parse
        from termaid.renderer.draw import render_graph_canvas

        graph = parse("graph LR\n  A --> B")
        canvas = render_graph_canvas(graph)
        assert canvas is not None

        pairs = canvas.to_styled_pairs()
        styles_used = set()
        for row in pairs:
            for ch, style in row:
                if style:
                    styles_used.add(style)

        assert "node" in styles_used, "Should have 'node' style"
        assert "edge" in styles_used or "arrow" in styles_used, (
            "Should have edge or arrow styles"
        )


class TestRichRendering:
    """Test Rich rendering with themes (only if rich is installed)."""

    @pytest.fixture(autouse=True)
    def _skip_without_rich(self):
        pytest.importorskip("rich")

    def test_render_rich_returns_text(self):
        from termaid import render_rich
        result = render_rich("graph LR\n  A --> B")
        from rich.text import Text
        assert isinstance(result, Text)

    def test_render_rich_contains_labels(self):
        from termaid import render_rich
        result = render_rich("graph LR\n  A --> B")
        plain = result.plain
        assert "A" in plain
        assert "B" in plain

    def test_render_rich_with_theme(self):
        from termaid import render_rich
        result = render_rich("graph LR\n  A --> B", theme="terra")
        assert "A" in result.plain
        assert "B" in result.plain

    @pytest.mark.parametrize("theme", ["default", "terra", "neon", "mono", "amber", "phosphor"])
    def test_all_themes_render(self, theme: str):
        from termaid import render_rich
        result = render_rich("graph LR\n  A --> B", theme=theme)
        assert "A" in result.plain
        assert "B" in result.plain

    def test_class_color_tints_the_label(self):
        from termaid import render_rich
        source = (
            "graph LR\n  A[alpha] --> B[bravo]\n"
            "  classDef bad stroke:#ff0000,color:#ff0000\n  class B bad"
        )
        result = render_rich(source, theme="mono")
        assert _styles_at(result, result.plain.index("bravo")) == ["#ff0000"]
        assert _styles_at(result, result.plain.index("alpha")) == ["white"]

    def test_class_without_color_keeps_the_theme_label(self):
        from termaid import render_rich
        source = "graph LR\n  A[alpha] --> B[bravo]\n  classDef bad stroke:#ff0000\n  class B bad"
        result = render_rich(source, theme="mono")
        assert _styles_at(result, result.plain.index("bravo")) == ["white"]


def _styles_at(text, index: int) -> list[str]:
    return [str(span.style) for span in text.spans if span.start <= index < span.end]
