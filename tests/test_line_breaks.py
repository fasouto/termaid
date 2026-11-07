"""<br> breaks a line in every kind of label, as in Mermaid."""
from __future__ import annotations

import pytest

from termaid import render
from termaid.utils import line_breaks


def _rows(source: str) -> list[str]:
    return [row.strip(" │┆") for row in render(source).splitlines()]


@pytest.mark.parametrize("tag", ["<br>", "<br/>", "<br />", "<BR>", " <br/> "])
def test_line_breaks_helper(tag):
    assert line_breaks(f"one{tag}two") == "one\ntwo"
    assert line_breaks(f"one{tag}two", " ") == "one two"


@pytest.mark.parametrize(
    "source",
    [
        "flowchart LR\n  A -->|sends the<br/>request| B",
        "flowchart TD\n  A -->|sends the<br/>request| B",
        'flowchart TD\n  A -- "sends the<br>request" --> B',
        "flowchart TD\n  A -- sends the<br>request --> B",
        "sequenceDiagram\n  A->>B: sends the<br/>request",
        "stateDiagram-v2\n  S1 --> S2: sends the<br/>request",
    ],
)
def test_edge_and_message_labels_break(source):
    out = render(source)
    assert "<br" not in out
    rows = "\n".join(_rows(source))
    assert "sends the" in rows and "request" in rows
    assert "sends the request" not in rows  # on two lines


def test_sequence_participant_breaks():
    out = render("sequenceDiagram\n  participant A as Agent<br/>(Claude)\n  A->>B: hi")
    assert "<br" not in out
    assert any("Agent" in row and "Claude" not in row for row in out.splitlines())


def test_state_alias_label_breaks():
    out = render('stateDiagram-v2\n  state "one<br/>two" as X\n  X --> Y')
    assert "<br" not in out
    assert any(row.strip(" │") == "one" for row in out.splitlines())


@pytest.mark.parametrize(
    "source",
    [
        'flowchart TD\n  subgraph S["Top<br/>layer"]\n    A --> B\n  end',
        'flowchart TD\n  subgraph S [Top<br/>layer]\n    A --> B\n  end',
        'erDiagram\n  A ||--o{ B : "Top<br/>layer"',
    ],
)
def test_one_row_labels_get_a_space(source):
    """Subgraph titles and ER relationship labels have one row, so <br> reads as a space."""
    out = render(source)
    assert "<br" not in out
    assert "Top layer" in out


def test_quoted_text_form_edge_label_keeps_its_text():
    """`-- "text" -->` used to draw only the quotes, with the text blanked out."""
    out = render('flowchart TD\n  A -- "sends request" --> B')
    assert "sends request" in out
    assert '"' not in out


def test_subgraph_id_and_label_without_a_space():
    out = render('flowchart TD\n  subgraph S["Top layer"]\n    A --> B\n  end')
    assert "Top layer" in out
    assert 'S["' not in out


def test_wrapping_measures_each_line():
    """With a width, a label already split by <br> wraps line by line."""
    out = render("flowchart LR\n  A -->|short<br/>also short| B", max_label_width=12)
    assert "short" in out and "also short" in out
