"""Tests for XY chart diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.xychart import parse_xychart


class TestXYChartParser:
    def test_bar_chart(self):
        d = parse_xychart(
            'xychart-beta\n'
            '    x-axis [Q1, Q2, Q3, Q4]\n'
            '    bar [10, 25, 18, 32]\n'
        )
        assert d.datasets[0].chart_type == "bar"
        assert d.datasets[0].values == [10, 25, 18, 32]
        assert d.x_categories == ["Q1", "Q2", "Q3", "Q4"]

    def test_line_chart(self):
        d = parse_xychart(
            'xychart-beta\n'
            '    x-axis [Jan, Feb, Mar]\n'
            '    line [5, 12, 8]\n'
        )
        assert d.datasets[0].chart_type == "line"
        assert d.datasets[0].values == [5, 12, 8]

    def test_combo(self):
        d = parse_xychart(
            'xychart-beta\n'
            '    x-axis [A, B, C]\n'
            '    bar [10, 20, 30]\n'
            '    line [5, 15, 25]\n'
        )
        assert len(d.datasets) == 2
        assert d.datasets[0].chart_type == "bar"
        assert d.datasets[1].chart_type == "line"

    def test_horizontal(self):
        d = parse_xychart(
            'xychart-beta horizontal\n'
            '    x-axis [A, B]\n'
            '    bar [10, 20]\n'
        )
        assert d.horizontal is True

    def test_title_and_axes(self):
        d = parse_xychart(
            'xychart-beta\n'
            '    title "Revenue Report"\n'
            '    x-axis "Month" [Jan, Feb, Mar]\n'
            '    y-axis "Revenue (M)" 0 --> 50\n'
            '    bar [10, 20, 30]\n'
        )
        assert d.title == "Revenue Report"
        assert d.x_label == "Month"
        assert d.y_label == "Revenue (M)"
        assert d.y_range == (0, 50)


class TestXYChartRendering:
    def test_bar_chart(self):
        output = render(
            'xychart-beta\n'
            '    title "Sales"\n'
            '    x-axis [Q1, Q2, Q3, Q4]\n'
            '    y-axis 0 --> 100\n'
            '    bar [40, 55, 70, 90]\n'
        )
        assert "Sales" in output
        assert "Q1" in output
        assert "Q4" in output
        assert "█" in output

    def test_horizontal_bar(self):
        output = render(
            'xychart-beta horizontal\n'
            '    x-axis [Backend, Frontend, DevOps]\n'
            '    y-axis 0 --> 15\n'
            '    bar [12, 8, 5]\n'
        )
        assert "Backend" in output
        assert "█" in output

    def test_combo(self):
        output = render(
            'xychart-beta\n'
            '    x-axis [Jan, Feb, Mar]\n'
            '    y-axis 0 --> 100\n'
            '    bar [30, 50, 80]\n'
            '    line [30, 50, 80]\n'
        )
        assert "Jan" in output
        assert "█" in output
