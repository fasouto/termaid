"""Tests for the arrowhead style option (``arrow_style``)."""
import pytest

from termaid import render, render_styled
from termaid.cli import main
from termaid.renderer.charset import ARROW_STYLES, ASCII, UNICODE, build_charset

FLOW = "flowchart {d}\n    A --> B\n    B --> C"


def glyphs(output: str) -> set[str]:
    every = {glyph for heads in ARROW_STYLES.values() for glyph in heads}
    return {ch for ch in output if ch in every}


class TestFlowchartArrows:
    @pytest.mark.parametrize("style", ["pointer", "triangle", "outline"])
    @pytest.mark.parametrize("direction, index", [("LR", 0), ("RL", 1), ("TD", 2), ("BT", 3)])
    def test_style_in_every_direction(self, style, direction, index):
        output = render(FLOW.format(d=direction), arrow_style=style)
        assert glyphs(output) == {ARROW_STYLES[style][index]}, output

    def test_default_is_pointer(self):
        assert render(FLOW.format(d="LR")) == render(FLOW.format(d="LR"), arrow_style="pointer")
        assert "►" in render(FLOW.format(d="LR"))

    def test_back_edges_use_the_style(self):
        output = render("flowchart LR\n    A --> B\n    B --> A", arrow_style="triangle")
        assert glyphs(output) == {"▶", "▲"}, output

    def test_ascii_ignores_style(self):
        source = FLOW.format(d="LR")
        assert render(source, use_ascii=True, arrow_style="outline") == render(source, use_ascii=True)

    def test_unknown_style(self):
        with pytest.raises(ValueError, match="unknown arrow style"):
            render(FLOW.format(d="LR"), arrow_style="fancy")

    def test_styles_are_independent_per_call(self):
        assert "▷" in render(FLOW.format(d="LR"), arrow_style="outline")
        assert "►" in render(FLOW.format(d="LR"))

    def test_styled_output(self):
        doc = render_styled(FLOW.format(d="LR"), arrow_style="triangle")
        arrows = {c["text"] for line in doc["lines"] for c in line if c["style"] == "arrow"}
        assert arrows == {"▶"}, arrows


class TestOtherDiagrams:
    SEQUENCE = "sequenceDiagram\n    A->>B: hi\n    B-->>A: back\n    A<<->>B: both\n    A->>A: self"

    @pytest.mark.parametrize("style", ["pointer", "triangle", "outline"])
    def test_sequence(self, style):
        right, left, _, _ = ARROW_STYLES[style]
        assert glyphs(render(self.SEQUENCE, arrow_style=style)) == {right, left}

    def test_class_diagram_outline_keeps_solid_dependency_arrows(self):
        source = "classDiagram\n    A --> B\n    C <|-- D"
        output = render(source, arrow_style="outline")
        assert "▼" in output  # dependency stays solid...
        assert "△" in output  # ...so it can't be mistaken for inheritance

    def test_class_diagram_triangle(self):
        assert "▼" in render("classDiagram\n    A --> B", arrow_style="triangle")

    def test_journey(self):
        source = "journey\n    title Day\n    section Work\n      Code: 5: Me\n      Test: 3: Me"
        assert "▶" in render(source, arrow_style="triangle")
        assert "►" in render(source)


class TestCli:
    def test_flag(self, capsys, tmp_path):
        path = tmp_path / "d.mmd"
        path.write_text(FLOW.format(d="LR"))
        assert main([str(path), "--arrow-style", "outline"]) == 0
        assert glyphs(capsys.readouterr().out) == {"▷"}

    def test_flag_with_width_fitting(self, capsys, tmp_path):
        path = tmp_path / "d.mmd"
        path.write_text(FLOW.format(d="LR"))
        assert main([str(path), "--arrow-style", "triangle", "--width", "30"]) == 0
        assert glyphs(capsys.readouterr().out) == {"▶"}

    def test_list(self, capsys):
        assert main(["--arrow-styles"]) == 0
        out = capsys.readouterr().out
        assert all(name in out for name in ARROW_STYLES)


class TestBuildCharset:
    def test_pointer_and_ascii_are_the_builtin_sets(self):
        assert build_charset() is UNICODE
        assert build_charset(True, "outline") is ASCII

    def test_dependency_never_looks_like_inheritance(self):
        for style in ARROW_STYLES:
            cs = build_charset(False, style)
            for d in ("right", "left", "down", "up"):
                assert getattr(cs, f"dependency_{d}") != getattr(cs, f"inherit_{d}"), (style, d)

    def test_unknown_style(self):
        with pytest.raises(ValueError, match="pointer, triangle, outline"):
            build_charset(False, "fancy")
