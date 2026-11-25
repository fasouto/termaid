"""Tests for quadrant chart diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.quadrant import parse_quadrant


class TestQuadrantParser:
    def test_full_chart(self):
        d = parse_quadrant(
            'quadrantChart\n'
            '    title Priority Matrix\n'
            '    x-axis Low Effort --> High Effort\n'
            '    y-axis Low Impact --> High Impact\n'
            '    quadrant-1 Do First\n'
            '    quadrant-2 Plan\n'
            '    quadrant-3 Delegate\n'
            '    quadrant-4 Skip\n'
            '    Cache: [0.2, 0.8]\n'
            '    Rewrite: [0.9, 0.3]\n'
        )
        assert d.title == "Priority Matrix"
        assert d.quadrant_1 == "Do First"
        assert d.quadrant_2 == "Plan"
        assert len(d.points) == 2
        assert d.points[0].label == "Cache"
        assert d.points[0].x == 0.2
        assert d.points[0].y == 0.8

    def test_data_point_coordinates(self):
        d = parse_quadrant(
            'quadrantChart\n'
            '    A: [0.1, 0.9]\n'
            '    B: [0.5, 0.5]\n'
            '    C: [0.9, 0.1]\n'
        )
        assert len(d.points) == 3
        assert d.points[2].x == 0.9
        assert d.points[2].y == 0.1


class TestQuadrantRendering:
    def test_render_full(self):
        output = render(
            'quadrantChart\n'
            '    title Priority\n'
            '    x-axis Low --> High\n'
            '    y-axis Low --> High\n'
            '    quadrant-1 Do First\n'
            '    quadrant-2 Plan\n'
            '    quadrant-3 Delegate\n'
            '    quadrant-4 Skip\n'
            '    Cache: [0.3, 0.85]\n'
            '    DB: [0.75, 0.25]\n'
        )
        assert "Priority" in output
        assert "Do First" in output
        assert "Plan" in output
        assert "Cache" in output
        assert "DB" in output
        assert "●" in output  # data point marker


class TestMalformedQuadrantInput:
    def test_invalid_coordinate_does_not_crash(self):
        qc = parse_quadrant(
            "quadrantChart\n"
            "    Bad: [0.1.2, 0.5]\n"
            "    Good: [0.2, 0.3]"
        )
        assert [p.label for p in qc.points] == ["Good"]


DOCS_EXAMPLE = (
    "quadrantChart\n"
    "    title Reach and engagement of campaigns\n"
    "    x-axis Low Reach --> High Reach\n"
    "    y-axis Low Engagement --> High Engagement\n"
    "    quadrant-1 We should expand\n"
    "    quadrant-2 Need to promote\n"
    "    quadrant-3 Re-evaluate\n"
    "    quadrant-4 May be improved\n"
    "    Campaign A: [0.3, 0.6]\n"
    "    Campaign B: [0.45, 0.23]\n"
    "    Campaign C: [0.57, 0.69]\n"
    "    Campaign D: [0.78, 0.34]\n"
    "    Campaign E: [0.40, 0.34]\n"
    "    Campaign F: [0.35, 0.78]\n"
)


class TestQuadrantText:
    def test_the_y_axis_label_is_drawn(self):
        out = render(DOCS_EXAMPLE)
        assert "Low Engagement" in out and "High Engagement" in out

    def test_every_label_and_quadrant_title_is_whole(self):
        out = render(DOCS_EXAMPLE)
        for text in ("We should expand", "Need to promote", "Re-evaluate", "May be improved"):
            assert text in out
        for name in "ABCDEF":
            assert f"Campaign {name}" in out
        assert out.count("●") == 6

    def test_a_class_on_a_point_is_not_drawn(self):
        out = render("quadrantChart\n    Point B:::hot: [0.2, 0.3]\n")
        assert ":::" not in out and "Point B" in out

    def test_a_long_quadrant_title_is_not_cut_by_the_axis(self):
        out = render(
            "quadrantChart\n"
            "    quadrant-1 Quick wins for the next sprint\n"
            "    quadrant-2 Major projects worth a look\n"
        )
        words = " ".join(out.replace("│", " ").split())
        for word in "Quick wins for the next sprint Major projects worth a look".split():
            assert f" {word} " in f" {words} "

    def test_br_tags_do_not_print(self):
        out = render("quadrantChart\n    title A<br/>B\n    quadrant-1 C<br>D\n    P<br>Q: [0.2, 0.3]\n")
        assert "<br" not in out
