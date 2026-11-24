"""A quoted label may span lines in the source, as in Mermaid's Markdown
strings; each source line becomes a line of the label."""
from __future__ import annotations

import pytest

from termaid import render
from tests.conftest import edge_targets, find_box


def assert_label_lines(out: str, label_lines: list[str]) -> None:
    """The lines are drawn one under the other inside one box."""
    lines = out.split("\n")
    top, bottom, left, right = find_box(lines, label_lines[0])
    row = next(r for r in range(top, bottom) if label_lines[0] in lines[r][left:right + 1])
    for i, text in enumerate(label_lines[1:], 1):
        inside = lines[row + i][left + 1:right]
        assert text in inside, f"Line {text!r} is not under {label_lines[0]!r} in its box:\n{out}"


@pytest.mark.parametrize("d", ["LR", "TD"])
def test_markdown_string_over_two_lines(d):
    out = render(f'flowchart {d}\n  a["`The **cat**\n  in the hat`"] --> b\n')
    assert "`" not in out and '["' not in out, out
    assert_label_lines(out, ["The cat", "in the hat"])
    assert edge_targets(out.split("\n"), "The cat", ["The cat", "b"]) == {"b"}, out


def test_markdown_string_over_three_lines():
    src = (
        "flowchart LR\n"
        '    markdown["`This **is** _Markdown_`"]\n'
        '    newLines["`Line1\n    Line 2\n    Line 3`"]\n'
        "    markdown --> newLines\n"
    )
    out = render(src)
    assert "`" not in out and '["' not in out, out
    assert_label_lines(out, ["Line1", "Line 2", "Line 3"])


def test_plain_string_over_two_lines():
    out = render('flowchart LR\n  a["The cat\n  in the hat"] --> b\n')
    assert '["' not in out, out
    assert_label_lines(out, ["The cat", "in the hat"])
    assert edge_targets(out.split("\n"), "The cat", ["The cat", "b"]) == {"b"}, out


def test_unclosed_quote_leaves_the_rest_of_the_diagram():
    out = render('flowchart LR\n  a["oops] --> b\n  c --> d\n  d --> e\n')
    lines = out.split("\n")
    assert edge_targets(lines, "c", ["c", "d", "e"]) == {"d"}, out
    assert edge_targets(lines, "d", ["c", "d", "e"]) == {"e"}, out


def test_long_markdown_label_wraps_inside_its_box():
    out = render('flowchart LR\n  a["`The **cat** is a very long label that wraps around`"] --> b\n')
    assert_label_lines(out, ["The cat is a very", "long label that", "wraps around"])
    labels = ["The cat is a very", "b"]
    assert edge_targets(out.split("\n"), labels[0], labels) == {"b"}, out
