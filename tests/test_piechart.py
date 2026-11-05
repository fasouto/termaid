"""Tests for pie chart diagram parsing and rendering (as bar charts)."""
from __future__ import annotations

from termaid import render
from termaid.parser.piechart import parse_pie_chart


# ── Parser tests ──────────────────────────────────────────────────────────────


class TestPieChartParser:
    def test_basic_slices(self):
        d = parse_pie_chart(
            'pie\n'
            '    "Dogs" : 386\n'
            '    "Cats" : 85\n'
            '    "Rats" : 15'
        )
        assert len(d.slices) == 3
        assert d.slices[0].label == "Dogs"
        assert d.slices[0].value == 386
        assert d.slices[1].label == "Cats"
        assert d.slices[1].value == 85
        assert d.slices[2].label == "Rats"
        assert d.slices[2].value == 15

    def test_title(self):
        d = parse_pie_chart(
            'pie\n'
            '    title Pets adopted by volunteers\n'
            '    "Dogs" : 386'
        )
        assert d.title == "Pets adopted by volunteers"

    def test_show_data_flag(self):
        d = parse_pie_chart(
            'pie showData\n'
            '    "A" : 50\n'
            '    "B" : 50'
        )
        assert d.show_data is True

    def test_show_data_absent(self):
        d = parse_pie_chart(
            'pie\n'
            '    "A" : 50'
        )
        assert d.show_data is False

    def test_decimal_values(self):
        d = parse_pie_chart(
            'pie\n'
            '    "Calcium" : 42.96\n'
            '    "Potassium" : 50.05'
        )
        assert d.slices[0].value == 42.96
        assert d.slices[1].value == 50.05

    def test_integer_values(self):
        d = parse_pie_chart(
            'pie\n'
            '    "Iron" : 5'
        )
        assert d.slices[0].value == 5.0

    def test_empty_pie(self):
        d = parse_pie_chart("pie")
        assert len(d.slices) == 0
        assert d.title == ""

    def test_comments_ignored(self):
        d = parse_pie_chart(
            'pie\n'
            '    %% this is a comment\n'
            '    "A" : 10\n'
            '    %% another comment'
        )
        assert len(d.slices) == 1

    def test_blank_lines_ignored(self):
        d = parse_pie_chart(
            'pie\n'
            '\n'
            '    "A" : 30\n'
            '\n'
            '    "B" : 70\n'
        )
        assert len(d.slices) == 2

    def test_warnings_on_unrecognized_lines(self):
        d = parse_pie_chart(
            'pie\n'
            '    "A" : 10\n'
            '    this is garbage'
        )
        assert len(d.warnings) == 1
        assert "Unrecognized" in d.warnings[0]

    def test_title_with_show_data(self):
        d = parse_pie_chart(
            'pie showData\n'
            '    title Key elements\n'
            '    "Calcium" : 42.96'
        )
        assert d.show_data is True
        assert d.title == "Key elements"

    def test_single_slice(self):
        d = parse_pie_chart(
            'pie\n'
            '    "Only" : 100'
        )
        assert len(d.slices) == 1

    def test_many_slices(self):
        lines = ['pie']
        for i in range(8):
            lines.append(f'    "Item {i}" : {(i + 1) * 10}')
        d = parse_pie_chart("\n".join(lines))
        assert len(d.slices) == 8


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestPieChartRendering:
    def test_basic_renders_with_labels(self):
        output = render(
            'pie\n'
            '    "Dogs" : 386\n'
            '    "Cats" : 85\n'
            '    "Rats" : 15'
        )
        assert "Dogs" in output
        assert "Cats" in output
        assert "Rats" in output

    def test_title_displayed(self):
        output = render(
            'pie\n'
            '    title Pets adopted\n'
            '    "Dogs" : 386\n'
            '    "Cats" : 85'
        )
        assert "Pets adopted" in output

    def test_title_on_pie_line_displayed(self):
        output = render(
            'pie title Pets adopted by volunteers\n'
            '    "Dogs" : 386\n'
            '    "Cats" : 85'
        )
        assert "Pets adopted by volunteers" in output

    def test_show_data_and_title_on_pie_line(self):
        output = render(
            'pie showData title Key elements\n'
            '    "Calcium" : 42.96\n'
            '    "Iron" : 5'
        )
        assert "Key elements" in output
        assert "[42.96]" in output

    def test_show_data_displays_values(self):
        output = render(
            'pie showData\n'
            '    "Calcium" : 42.96\n'
            '    "Iron" : 5'
        )
        assert "42.96" in output
        assert "Calcium" in output

    def test_percentages_displayed(self):
        output = render(
            'pie\n'
            '    "Big" : 75\n'
            '    "Small" : 25'
        )
        assert "75.0%" in output
        assert "25.0%" in output

    def test_distinct_fill_chars_per_slice(self):
        output = render(
            'pie\n'
            '    "First" : 50\n'
            '    "Second" : 50'
        )
        assert "█" in output
        assert "░" in output

    def test_bar_separator_char(self):
        output = render(
            'pie\n'
            '    "A" : 100'
        )
        assert "┃" in output

    def test_larger_slice_has_longer_bar(self):
        output = render(
            'pie\n'
            '    "Big" : 90\n'
            '    "Small" : 10'
        )
        lines = output.split("\n")
        # Find the individual bar lines (contain ┃)
        big_line = next(l for l in lines if "Big" in l and "┃" in l)
        small_line = next(l for l in lines if "Small" in l and "┃" in l)
        big_bar_len = big_line.count("█")
        small_bar_len = small_line.count("░")
        assert small_bar_len > 0
        assert big_bar_len > small_bar_len

    def test_ascii_mode(self):
        output = render(
            'pie\n'
            '    "Dogs" : 386\n'
            '    "Cats" : 85',
            use_ascii=True,
        )
        assert "Dogs" in output
        assert "Cats" in output
        assert "#" in output
        assert "*" in output
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋█▓░▒")
        for ch in output:
            assert ch not in unicode_chars

    def test_empty_pie_renders(self):
        output = render("pie")
        assert isinstance(output, str)

    def test_single_slice_renders(self):
        output = render(
            'pie\n'
            '    "All" : 100'
        )
        assert "All" in output
        assert "100.0%" in output

    def test_many_slices_render(self):
        lines = ['pie']
        for i in range(7):
            lines.append(f'    "Item{i}" : {(i + 1) * 10}')
        output = render("\n".join(lines))
        for i in range(7):
            assert f"Item{i}" in output

    def test_frontmatter_with_pie(self):
        output = render(
            '---\nconfig:\n  pie:\n    textPosition: 0.5\n---\n'
            'pie showData\n'
            '    title Test\n'
            '    "A" : 60\n'
            '    "B" : 40'
        )
        assert "Test" in output
        assert "A" in output
        assert "B" in output

    def test_labels_right_aligned(self):
        """Shorter labels should be padded to align with longer ones."""
        output = render(
            'pie\n'
            '    "Short" : 50\n'
            '    "Very Long Label" : 50'
        )
        lines = output.split("\n")
        short_line = next(l for l in lines if "Short" in l and "┃" in l)
        long_line = next(l for l in lines if "Very Long Label" in l and "┃" in l)
        # The bar separator ┃ should be at the same column
        assert short_line.index("┃") == long_line.index("┃")


def _stacked_bar(output: str) -> str:
    return next(l for l in output.split("\n") if "█" in l and "┃" not in l).strip()


class TestPieChartStackedBar:
    def test_every_slice_gets_a_segment(self):
        output = render(
            'pie\n'
            '    "Big" : 97\n'
            '    "One" : 1\n'
            '    "Two" : 2'
        )
        full = _stacked_bar(render('pie\n    "All" : 1'))
        bar = _stacked_bar(output)
        assert set(bar) == {"█", "░", "▒"}
        assert len(bar) == len(full)


def _stacked_label_row(output: str) -> str:
    lines = output.split("\n")
    stacked = next(i for i, l in enumerate(lines) if "█" in l and "┃" not in l)
    return lines[stacked + 1]


class TestPieChartStackedLabels:
    def test_only_percentages_when_any_name_does_not_fit(self):
        output = render(
            'pie title Fixes by area\n'
            '    "Block diagrams" : 2\n'
            '    "Labels" : 2\n'
            '    "Claude hook" : 2'
        )
        assert _stacked_label_row(output).split() == ["33%", "33%", "33%"]

    def test_every_name_when_all_names_fit(self):
        output = render(
            'pie\n'
            '    "Dogs" : 50\n'
            '    "Cats" : 30\n'
            '    "Rats" : 20'
        )
        assert _stacked_label_row(output).split() == [
            "Dogs", "50%", "Cats", "30%", "Rats", "20%",
        ]


class TestWideText:
    def test_wide_slice_names_are_whole(self):
        out = render('pie\n    "日本語テキスト" : 90\n    "B" : 10\n    "🍕 Pizza" : 5')
        assert "日本語テキスト┃" in out
        assert "🍕 Pizza┃" in out

    def test_title_wider_than_the_bars_is_whole(self):
        title = "A title that is a good deal wider than the forty-cell bar and its labels"
        assert title in render(f'pie title {title}\n    "A" : 1\n    "B" : 1')
