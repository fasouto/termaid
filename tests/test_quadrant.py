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
