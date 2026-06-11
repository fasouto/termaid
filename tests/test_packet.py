"""Tests for packet diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.packet import parse_packet


class TestPacketParser:
    def test_fields_and_ranges(self):
        d = parse_packet(
            'packet-beta\n'
            '    0-15: "Source Port"\n'
            '    16-31: "Dest Port"\n'
            '    32-63: "Sequence Number"\n'
        )
        assert len(d.fields) == 3
        assert d.fields[0].label == "Source Port"
        assert d.fields[0].start == 0
        assert d.fields[0].end == 15
        assert d.fields[1].start == 16
        assert d.fields[2].end == 63

    def test_single_bit_field(self):
        d = parse_packet(
            'packet-beta\n'
            '    0-15: "Port"\n'
            '    16: "Flag"\n'
        )
        assert d.fields[1].start == 16
        assert d.fields[1].end == 16


class TestPacketRendering:
    def test_render_udp(self):
        output = render(
            'packet-beta\n'
            '    0-15: "Source Port"\n'
            '    16-31: "Destination Port"\n'
            '    32-47: "Length"\n'
            '    48-63: "Checksum"\n'
        )
        assert "Source Port" in output
        assert "Destination Port" in output
        assert "Length" in output
        assert "Checksum" in output
        assert "╭" in output  # rounded box


class TestPacketWideChars:
    def test_cjk_label_does_not_overflow_borders(self):
        from termaid.utils import display_width
        output = render(
            'packet-beta\n'
            '  0-3: "源端口字段名称很长"\n'
            '  4-15: "Rest"'
        )
        lines = output.split("\n")
        border_w = max(display_width(l) for l in lines if "╭" in l or "┌" in l)
        assert all(display_width(l) <= border_w for l in lines)
        # The truncated label must not destroy the field borders: the
        # content row keeps its left border, field separator, and right border
        content_row = next(l for l in lines if "Rest" in l)
        assert content_row.count("│") >= 3
