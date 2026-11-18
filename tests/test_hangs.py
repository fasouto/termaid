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
