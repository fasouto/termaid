"""Tests for drawing the start of a diagram while the rest is still arriving (partial=True)."""
import json
from pathlib import Path

import pytest

from termaid import parse, render, render_styled
from termaid.partial import complete_partial

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "last_line, expected",
    [
        ("  B -->|ye", "  B"),                          # edge label still being typed
        ("  A -->|yes|", "  A"),                        # label done, no target yet
        ("  A -->|yes| B", "  A -->|yes| B"),           # complete
        ("  A --> B -->", "  A --> B"),                 # trailing link, no target
        ("  A --> B --", "  A --> B"),
        ("  A -- te", "  A"),                           # text link still being typed
        ("  A[Start] -", "  A[Start]"),                 # operator still being typed
        ("  A -.", "  A"),
        ("  A --> C[Send sess", "  A --> C[Send sess]"),  # label grows
        ('  A --> B["quoted lab', '  A --> B["quoted lab"]'),
        ("  A([Sta", "  A([Sta])"),
        ("  A[(Data", "  A[(Data)]"),
        ("  A --> Bo", "  A --> Bo"),                   # node id still being typed
        ("  Done --> [", "  Done"),                     # [*] being typed
    ],
)
def test_flowchart_lines(last_line, expected):
    completed = complete_partial(f"graph TD\n  X --> Y\n{last_line}")
    assert completed.splitlines()[-1] == expected


def test_line_held_back_entirely():
    assert complete_partial("graph TD\n  X --> Y\n  -->") == "graph TD\n  X --> Y"


@pytest.mark.parametrize(
    "last_line, kept",
    [("  A->>", False), ("  A->>B", False), ("  A->>B: Hi the", True), ("  participant Al", True)],
)
def test_sequence_lines(last_line, kept):
    completed = complete_partial(f"sequenceDiagram\n  A->>B: hi\n{last_line}")
    assert (completed.splitlines()[-1] == last_line) is kept


@pytest.mark.parametrize("kind, line", [("erDiagram", "  A ||--o{ B : ha"), ("classDiagram", "  A <|--")])
def test_er_and_class_wait_for_the_whole_line(kind, line):
    assert complete_partial(f"{kind}\n  X\n{line}") == f"{kind}\n  X"


def test_other_types_close_brackets_and_drop_half_arrows():
    assert complete_partial("quadrantChart\n  title T\n  x-axis Low --").endswith("x-axis Low")
    assert complete_partial("quadrantChart\n  title T\n  A: [0.3, 0.").endswith("A: [0.3, 0.]")


def test_complete_source_is_unchanged():
    source = "graph TD\n  A --> C[Send sess\n"  # ends with a newline: the line is finished
    assert complete_partial(source) == source
    assert complete_partial("graph TD") == "graph TD"


def test_crlf():
    assert complete_partial("graph TD\r\n  A --> B -->") == "graph TD\n  A --> B"


def test_render_and_parse_take_partial():
    source = "graph TD\n  A[Start] --> B{Ok?}\n  B -->|ye"
    assert "|ye" in render(source)  # today's behaviour: syntax becomes a node
    assert "|ye" not in render(source, partial=True)
    assert "ye" not in json.dumps(render_styled(source, partial=True))
    assert set(parse(source, partial=True).nodes) == {"A", "B"}


def test_default_is_unchanged():
    source = "graph TD\n  A --> C[Send sess"
    assert render(source) == render(source, partial=False)


def _no_new_syntax(source: str) -> bool:
    """Every streamed prefix draws nothing the finished diagram doesn't."""
    tokens = ["-->", "->>", "-.-", "==>", "--", "[", "]", "{", "}", "|", ":::", '"', "(", ")"]
    final = render(source)
    for end in range(source.index("\n") + 1, len(source) + 1):
        out = render(source[:end], partial=True)
        if any(token in out and token not in final for token in tokens):
            return False
    return True


@pytest.mark.parametrize(
    "fixture",
    sorted((FIXTURES / "flowcharts").glob("*.mmd"))[:25] + sorted((FIXTURES / "sequence").glob("*.mmd"))[:8],
    ids=lambda p: p.stem,
)
def test_streaming_fixtures_draw_no_raw_syntax(fixture):
    assert _no_new_syntax(fixture.read_text().rstrip("\n"))


@pytest.mark.parametrize(
    "line",
    ["A -- t " * 2000, "C[" + "word " * 2000, "C " + "-" * 14000 + "x y"],
    ids=["text links", "long label", "long link"],
)
def test_very_long_unfinished_line_is_quick(line):
    import time

    source = "graph LR\n  A --> B\n  " + line
    start = time.perf_counter()
    completed = complete_partial(source)
    assert time.perf_counter() - start < 0.05
    assert completed == "graph LR\n  A --> B"
