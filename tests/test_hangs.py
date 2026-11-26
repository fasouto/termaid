"""Inputs that once never finished (issue #51, H1 to H4)."""
from __future__ import annotations

import threading

import pytest

from termaid import parse, render
from termaid.parser.flowchart import parse_flowchart
from termaid.parser.packet import parse_packet


def finishes(fn, seconds: float = 20):
    """Run *fn* and return its result, failing the test rather than hanging the suite."""
    result: list = []
    worker = threading.Thread(target=lambda: result.append(fn()), daemon=True)
    worker.start()
    worker.join(seconds)
    assert result, f"still running after {seconds} s"
    return result[0]


def test_a_dense_flowchart_finishes():
    """Six sources into six targets leaves some edges with no route."""
    out = finishes(lambda: render("graph TD\n  A0 & A1 & A2 & A3 & A4 & A5 --> B0 & B1 & B2 & B3 & B4 & B5"))
    assert all(name in out for name in ("A0", "A5", "B0", "B5"))


def test_an_unmatched_star_in_a_markdown_label_is_text():
    graph = finishes(lambda: parse_flowchart('graph LR\n  A["`2*3`"]'))
    assert graph.nodes["A"].label == "2*3"


def test_markdown_emphasis_still_parses():
    graph = parse_flowchart('graph LR\n  A["`**bold** and *it* x*`"]')
    assert graph.nodes["A"].label == "bold and it x*"


def test_a_packet_field_far_from_bit_zero_draws_no_empty_rows():
    out = finishes(lambda: render('packet-beta\n  3200000: "x"'))
    assert len(out.splitlines()) < 50


def test_a_packet_field_after_a_gap_is_dropped_with_a_warning():
    packet = parse_packet('packet-beta\n  0-7: "a"\n  16-23: "b"')
    assert [f.label for f in packet.fields] == ["a"]
    assert any("16-23" in w for w in packet.warnings)


@pytest.mark.parametrize("link", ["=" * 3000, "-" * 3000, "-" * 3000 + ">|x|"])
def test_a_very_long_link_parses_quickly(link):
    graph = finishes(lambda: parse(f"graph LR\nA {link} B"), seconds=10)
    assert graph is not None


class TestReviewFindings:
    """Inputs an adversarial review of 0.15.0 found slow or never-ending."""

    def test_a_long_run_of_quote_marks_is_read_at_once(self):
        import time
        from termaid.claude_hook import StreamRenderer
        from termaid.utils import OPEN_FENCE
        start = time.perf_counter()
        assert OPEN_FENCE.match("> " * 2000 + "x") is None
        assert StreamRenderer(width=80).feed("> " * 200 + "x\n", final=True) == "> " * 200 + "x\n"
        assert time.perf_counter() - start < 1

    def test_a_fence_inside_quotes_is_still_found(self):
        from termaid.utils import OPEN_FENCE
        assert OPEN_FENCE.match("> > ```mermaid").group("indent", "fence", "info") == ("> > ", "```", "mermaid")
        assert OPEN_FENCE.match(" >  ~~~~").group("indent") == " >  "

    def test_a_class_line_of_blanks_is_read_at_once(self):
        import time
        from termaid import render
        start = time.perf_counter()
        render("classDiagram\nA" + " " * 20000 + "x")
        assert "many" in render('classDiagram\nA "1"   -->   "many"   B : has')
        assert time.perf_counter() - start < 1

    def test_a_packet_field_of_a_hundred_million_bits_is_not_drawn(self):
        import time
        from termaid import render
        start = time.perf_counter()
        assert render('packet-beta\n0-99999999: "x"\n') == ""
        out = render('packet-beta\n0-15: "Port"\n16-99999999: "x"\n')
        assert "Port" in out and len(out) < 2000
        assert time.perf_counter() - start < 1


def test_a_chart_value_that_is_not_a_number_keeps_its_place():
    from termaid import render
    out = render("xychart-beta\n x-axis [a,b,c]\n bar [1,x,3]\n")
    labels = out.split("\n")[-1]
    assert labels.split() == ["a", "b", "c"]
    column = labels.index("c")
    assert any(line[column:column + 1] == "█" for line in out.split("\n")), out
    assert not any(line[labels.index("b"):labels.index("b") + 1] == "█" for line in out.split("\n")), out
